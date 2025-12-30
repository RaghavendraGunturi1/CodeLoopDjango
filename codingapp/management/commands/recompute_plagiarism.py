# codingapp/management/commands/recompute_plagiarism.py
"""
Recompute plagiarism + similarity signals and (optionally) apply penalties.

This improved command:
 - recomputes per-submission 'plagiarism_percent' (max similarity to other submissions)
 - also computes token_similarity, structural_similarity, ai_generated_prob per submission
 - optionally applies per-submission penalty (uses apply_plagiarism_penalty)
 - optionally computes and writes assessment-level penalties into AssessmentSession

Usage examples:
  python manage.py recompute_plagiarism
  python manage.py recompute_plagiarism --assessment 5 --apply-penalty --apply-assessment-penalties
  python manage.py recompute_plagiarism --dry-run --verbose
"""
import json
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.db.models import Max, Sum

from codingapp.models import (
    AssessmentSubmission, Assessment, Question, AssessmentSession, AssessmentQuestion
)

# Helpers (preferred from utils)
try:
    from codingapp.utils import normalize_code, penalty_factor_from_plagiarism, compute_ensemble_plagiarism, apply_plagiarism_penalty
except Exception:
    # conservative fallback implementations
    import re
    def normalize_code(src: str, language: str = "") -> str:
        if not src:
            return ""
        s = src
        s = re.sub(r'(?m)#.*$', '', s)
        s = re.sub(r'(?m)//.*$', '', s)
        s = re.sub(r'/\*.*?\*/', '', s, flags=re.S)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def penalty_factor_from_plagiarism(pct, no_penalty_up_to=35.0, full_zero_at=85.0):
        p = float(pct or 0.0)
        if p <= no_penalty_up_to:
            return 1.0
        if p >= full_zero_at:
            return 0.0
        return round((full_zero_at - p) / (full_zero_at - no_penalty_up_to), 4)

    def compute_ensemble_plagiarism(code, other_codes, **kwargs):
        # minimal: compare with SequenceMatcher across normalized text and return token/struct as same value
        best = 0.0
        best_struct = 0.0
        best_token = 0.0
        best_ai = 0.0
        for other in other_codes:
            if not other:
                continue
            try:
                sim = SequenceMatcher(None, normalize_code(code), normalize_code(other)).ratio()
            except Exception:
                sim = 0.0
            if sim > best:
                best = sim
            # set token/struct same as best for fallback
            best_struct = best_token = best
        return {
            "token_similarity": round(best_token, 4),
            "structural_similarity": round(best_struct, 4),
            "embedding_similarity": round(best_struct, 4),
            "ai_generated_prob": round(best_ai, 4),
            "plag_percent": round(min(1.0, best) * 100.0, 2)
        }

    def apply_plagiarism_penalty(raw_marks, plagiarism_percent, code=None, question=None):
        # conservative linear fallback (same as earlier)
        if raw_marks <= 0:
            return 0
        p = float(plagiarism_percent or 0.0)
        if p <= 35.0:
            return raw_marks
        if p >= 85.0:
            return 0
        factor = (85.0 - p) / (85.0 - 35.0)
        return round(raw_marks * factor, 2)


class Command(BaseCommand):
    help = (
        "Recompute plagiarism_percent and similarity signals for AssessmentSubmission rows; optionally apply penalties.\n"
        "See help for flags."
    )

    def add_arguments(self, parser):
        parser.add_argument("--assessment", "-a", type=int, help="Limit to this assessment id", required=False)
        parser.add_argument("--question", "-q", type=int, help="Limit to this question id", required=False)
        parser.add_argument("--dry-run", action="store_true", help="Don't save changes, just print what would change")
        parser.add_argument("--apply-penalty", action="store_true", help="Also apply plagiarism penalty to per-submission score")
        parser.add_argument("--apply-assessment-penalties", action="store_true", help="Also compute and save assessment-level penalties to AssessmentSession")
        parser.add_argument("--verbose", action="store_true", help="Verbose output")

    def handle(self, *args, **options):
        assessment_id = options.get("assessment")
        question_id = options.get("question")
        dry_run = options.get("dry_run", False)
        apply_penalty_flag = options.get("apply_penalty", False)
        apply_assessment_penalties_flag = options.get("apply_assessment_penalties", False)
        verbose = options.get("verbose", False)

        if apply_penalty_flag and apply_plagiarism_penalty is None:
            self.stdout.write(self.style.WARNING("apply_plagiarism_penalty not available; --apply-penalty ignored"))
            apply_penalty_flag = False

        # filter submissions
        subs_qs = AssessmentSubmission.objects.all().select_related("user", "assessment", "question")
        if assessment_id:
            subs_qs = subs_qs.filter(assessment_id=assessment_id)
        if question_id:
            subs_qs = subs_qs.filter(question_id=question_id)

        # group by (assessment, question)
        groups = {}
        for s in subs_qs:
            key = (s.assessment_id, s.question_id)
            groups.setdefault(key, []).append(s)

        if not groups:
            self.stdout.write(self.style.NOTICE("No submissions found for filters"))
            return

        total_checked = 0
        total_updated = 0

        for (a_id, q_id), subs in groups.items():
            try:
                assessment = Assessment.objects.get(pk=a_id)
            except Assessment.DoesNotExist:
                assessment = None
            try:
                question = Question.objects.get(pk=q_id)
            except Question.DoesNotExist:
                question = None

            if verbose:
                self.stdout.write(f"Processing assessment={a_id} question={q_id} ({len(subs)} submissions)")

            # Precompute normalized codes & raw codes
            codes = []
            for s in subs:
                raw = s.code or ""
                norm = normalize_code(raw or "", "")
                codes.append((s.id, norm, s.user_id, raw))

            # For each submission compute max similarity and other signals against other codes
            for sub in subs:
                total_checked += 1
                my_raw = sub.code or ""
                my_norm = normalize_code(my_raw or "", "")

                if not my_norm:
                    new_plag = 0.0
                    token_sim = 0.0
                    struct_sim = 0.0
                    ai_prob = 0.0
                else:
                    # prepare list of other raw codes
                    other_raws = [other_raw for (oid, onorm, ouid, other_raw) in codes if oid != sub.id and other_raw]
                    if not other_raws:
                        new_plag = 0.0
                        token_sim = struct_sim = ai_prob = 0.0
                    else:
                        # compute ensemble signals comparing my_raw to all others and take best-match signals
                        try:
                            signals = compute_ensemble_plagiarism(my_raw, other_raws)
                            new_plag = float(signals.get("plag_percent", 0.0))
                            token_sim = float(signals.get("token_similarity", 0.0))
                            struct_sim = float(signals.get("structural_similarity", 0.0))
                            ai_prob = float(signals.get("ai_generated_prob", 0.0))
                        except Exception as e:
                            # fallback: use sequence matcher on normalized strings
                            max_sim = 0.0
                            best_token = 0.0
                            best_struct = 0.0
                            for other_id, other_norm, other_user, other_raw in codes:
                                if other_id == sub.id or not other_norm:
                                    continue
                                try:
                                    sim = SequenceMatcher(None, my_norm, other_norm).ratio()
                                except Exception:
                                    sim = 0.0
                                if sim > max_sim:
                                    max_sim = sim
                            new_plag = round(max_sim * 100.0, 2)
                            token_sim = struct_sim = round(max_sim, 4)
                            ai_prob = 0.0

                # reconstruct marks_before_penalty (simple inference from sub.output or sub.raw_score)
                marks_before_penalty = 0
                try:
                    # prefer explicit raw_score field if present
                    if hasattr(sub, "raw_score") and sub.raw_score is not None:
                        marks_before_penalty = float(sub.raw_score or 0.0)
                    else:
                        # infer from output JSON: full 5 if all testcases Accepted
                        results = json.loads(sub.output or "[]")
                        if results and all((r.get("status") == "Accepted") for r in results):
                            marks_before_penalty = 5.0
                        else:
                            marks_before_penalty = 0.0
                except Exception:
                    marks_before_penalty = 5.0 if (sub.score and float(sub.score) >= 5.0) else 0.0

                # compute new per-submission score if requested
                new_score = sub.score
                if apply_penalty_flag and apply_plagiarism_penalty:
                    try:
                        new_score = apply_plagiarism_penalty(marks_before_penalty, new_plag, code=sub.code, question=question)
                    except Exception:
                        new_score = marks_before_penalty

                # Compare and save if needed (or dry-run)
                if dry_run:
                    changed = False
                    msgs = []
                    if float(sub.plagiarism_percent or 0.0) != float(new_plag or 0.0):
                        changed = True
                        msgs.append(f"plag {sub.plagiarism_percent}->{new_plag}")
                    # save token/struct/ai decimal changes if your model stores them
                    if getattr(sub, "token_similarity", None) is not None and float(getattr(sub, "token_similarity") or 0.0) != float(token_sim or 0.0):
                        changed = True
                        msgs.append(f"token {getattr(sub,'token_similarity')}->{token_sim}")
                    if getattr(sub, "structural_similarity", None) is not None and float(getattr(sub, "structural_similarity") or 0.0) != float(struct_sim or 0.0):
                        changed = True
                        msgs.append(f"struct {getattr(sub,'structural_similarity')}->{struct_sim}")
                    if getattr(sub, "ai_generated_prob", None) is not None and float(getattr(sub, "ai_generated_prob") or 0.0) != float(ai_prob or 0.0):
                        changed = True
                        msgs.append(f"ai {getattr(sub,'ai_generated_prob')}->{ai_prob}")
                    if apply_penalty_flag and float(sub.score or 0) != float(new_score or 0):
                        changed = True
                        msgs.append(f"score {sub.score}->{new_score}")
                    if changed:
                        total_updated += 1
                        self.stdout.write(f"[DRY] submission id={sub.id} user={sub.user_id} changes: " + "; ".join(msgs))
                else:
                    updated_fields = []
                    with transaction.atomic():
                        if float(sub.plagiarism_percent or 0.0) != float(new_plag or 0.0):
                            sub.plagiarism_percent = new_plag
                            updated_fields.append("plagiarism_percent")
                        # write token/struct/ai if model fields exist
                        if hasattr(sub, "token_similarity"):
                            if float(getattr(sub, "token_similarity") or 0.0) != float(token_sim or 0.0):
                                sub.token_similarity = token_sim
                                updated_fields.append("token_similarity")
                        if hasattr(sub, "structural_similarity"):
                            if float(getattr(sub, "structural_similarity") or 0.0) != float(struct_sim or 0.0):
                                sub.structural_similarity = struct_sim
                                updated_fields.append("structural_similarity")
                        if hasattr(sub, "ai_generated_prob"):
                            if float(getattr(sub, "ai_generated_prob") or 0.0) != float(ai_prob or 0.0):
                                sub.ai_generated_prob = ai_prob
                                updated_fields.append("ai_generated_prob")

                        if apply_penalty_flag and float(sub.score or 0) != float(new_score or 0):
                            sub.score = new_score
                            updated_fields.append("score")

                        # update timestamp if present
                        if hasattr(sub, "updated_at"):
                            sub.updated_at = timezone.now()
                            updated_fields.append("updated_at")

                        if updated_fields:
                            sub.save(update_fields=updated_fields)
                            total_updated += 1
                            if verbose:
                                self.stdout.write(self.style.SUCCESS(f"Updated submission id={sub.id} user={sub.user_id}: plag={new_plag} token={token_sim} struct={struct_sim} ai={ai_prob} score={getattr(sub,'score',None)}"))

        # Step 2: assessment-level penalties (existing logic, unchanged but uses recomputed per-submission fields)
        if apply_assessment_penalties_flag:
            assessment_ids = sorted({a for (a, q) in groups.keys()})
            if assessment_id:
                assessment_ids = [assessment_id]

            for a_id in assessment_ids:
                try:
                    assessment = Assessment.objects.get(pk=a_id)
                except Assessment.DoesNotExist:
                    if verbose:
                        self.stdout.write(self.style.WARNING(f"Assessment {a_id} not found; skipping"))
                    continue

                # users who submitted or have a session
                user_ids = AssessmentSubmission.objects.filter(assessment=assessment).values_list('user_id', flat=True).distinct()
                session_user_ids = AssessmentSession.objects.filter(assessment=assessment).values_list('user_id', flat=True).distinct()
                user_ids = set(list(user_ids) + list(session_user_ids))

                if verbose:
                    self.stdout.write(f"Computing assessment-level penalties for assessment={a_id} users={len(user_ids)}")

                for uid in user_ids:
                    max_plag = AssessmentSubmission.objects.filter(assessment=assessment, user_id=uid).aggregate(max_p=Max('plagiarism_percent')).get('max_p') or 0.0
                    max_plag = float(max_plag or 0.0)

                    # sum coding raw (prefer raw_score field)
                    subs_user = AssessmentSubmission.objects.filter(assessment=assessment, user_id=uid)
                    coding_raw_total = 0.0
                    for s in subs_user:
                        raw_val = getattr(s, "raw_score", None)
                        if raw_val is None:
                            try:
                                results = json.loads(s.output or "[]")
                                all_passed = bool(results) and all((r.get("status") == "Accepted") for r in results)
                                raw_val = 5.0 if all_passed else 0.0
                            except Exception:
                                raw_val = 5.0 if (s.score == 5) else 0.0
                        coding_raw_total += float(raw_val or 0.0)

                    quiz_score = 0.0
                    if getattr(assessment, "quiz", None):
                        try:
                            from codingapp.models import QuizSubmission
                            best_q = QuizSubmission.objects.filter(quiz=assessment.quiz, user_id=uid).order_by("-score").first()
                            if best_q:
                                quiz_score = float(getattr(best_q, "score", 0) or 0.0)
                        except Exception:
                            quiz_score = 0.0

                    raw_total = round(quiz_score + coding_raw_total, 2)
                    factor = penalty_factor_from_plagiarism(max_plag)
                    penalized_total = round(raw_total * factor, 2)

                    sess = AssessmentSession.objects.filter(assessment=assessment, user_id=uid).first()
                    if sess is None:
                        if verbose:
                            self.stdout.write(self.style.WARNING(f"No AssessmentSession for assessment={a_id} user={uid}; skipping"))
                        continue

                    if dry_run:
                        msgs = []
                        if getattr(sess, "penalty_percent", None) != round(max_plag, 2):
                            msgs.append(f"penalty_percent: {getattr(sess, 'penalty_percent')} -> {round(max_plag,2)}")
                        if getattr(sess, "penalty_factor", None) != factor:
                            msgs.append(f"penalty_factor: {getattr(sess,'penalty_factor')} -> {factor}")
                        if getattr(sess, "raw_total", None) != raw_total:
                            msgs.append(f"raw_total: {getattr(sess,'raw_total')} -> {raw_total}")
                        if getattr(sess, "penalized_total", None) != penalized_total:
                            msgs.append(f"penalized_total: {getattr(sess,'penalized_total')} -> {penalized_total}")
                        if msgs:
                            total_updated += 1
                            self.stdout.write(f"[DRY] Session user={uid} changes: " + "; ".join(msgs))
                    else:
                        update_fields = []
                        with transaction.atomic():
                            if getattr(sess, "penalty_percent", None) != round(max_plag,2):
                                sess.penalty_percent = round(max_plag,2)
                                update_fields.append("penalty_percent")
                            if getattr(sess, "penalty_factor", None) != factor:
                                sess.penalty_factor = factor
                                update_fields.append("penalty_factor")
                            if getattr(sess, "raw_total", None) != raw_total:
                                sess.raw_total = raw_total
                                update_fields.append("raw_total")
                            if getattr(sess, "penalized_total", None) != penalized_total:
                                sess.penalized_total = penalized_total
                                update_fields.append("penalized_total")
                            if hasattr(sess, "penalty_applied"):
                                sess.penalty_applied = (factor < 1.0)
                                update_fields.append("penalty_applied")
                            if update_fields:
                                sess.save(update_fields=update_fields)
                                total_updated += 1
                                if verbose:
                                    self.stdout.write(self.style.SUCCESS(f"Updated session for user={uid} assessment={a_id}: penalty={round(max_plag,2)} factor={factor} raw_total={raw_total} penalized={penalized_total}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Checked {total_checked} submissions. {'(dry-run)' if dry_run else ''} Updated {total_updated} rows."))
