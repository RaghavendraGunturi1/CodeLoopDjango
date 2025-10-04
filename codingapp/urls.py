from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import (
    bulk_mcq_upload, ckeditor_upload, delete_notice, edit_notice, edit_profile, export_student_performance, 
    notice_list, add_notice, notice_detail, student_performance_detail, teacher_question_form
)

urlpatterns = [
    # Core Routes
    path('', views.home, name='home'),
    path('dashboard/', views.user_dashboard, name='dashboard'),
    path('questions/', views.question_list, name='question_list'),
    path('questions/<int:pk>/', views.question_detail, name='question_detail'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),

    # Authentication Routes
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('clear-splash-flag/', views.clear_splash_flag, name='clear_splash_flag'),

    # Module Routes
    path('modules/', views.module_list, name='module_list'),
    path('modules/<int:module_id>/', views.module_detail, name='module_detail'),
    path('modules/add/', views.add_module, name='add_module'),
    path('modules/<int:module_id>/edit/', views.edit_module, name='edit_module'),
    path('modules/<int:module_id>/delete/', views.delete_module, name='delete_module'),
    path('modules/<int:module_id>/add-question/', views.add_question_to_module, name='add_question'),

    # Assessment Routes
    path("assessments/", views.assessment_list, name="assessment_list"),
    path("assessments/<int:assessment_id>/", views.assessment_detail, name="assessment_detail"),
    path("assessments/<int:assessment_id>/leaderboard/", views.assessment_leaderboard, name="assessment_leaderboard"),
    path("assessments/<int:assessment_id>/questions/<int:question_id>/submit/", views.submit_assessment_code, name="submit_assessment_code"),

    # Teacher: Module Management
    path('teacher/modules/', views.teacher_module_list, name='teacher_module_list'),
    path('teacher/modules/add/', views.teacher_add_module, name='teacher_add_module'),
    path('teacher/modules/<int:module_id>/edit/', views.teacher_edit_module, name='teacher_edit_module'),
    path('teacher/modules/<int:module_id>/delete/', views.teacher_delete_module, name='teacher_delete_module'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),

    # Teacher: Question Management (with both new and legacy names)
    path('teacher/questions/', views.teacher_question_list, name='teacher_question_list'),
    # New DRY names
    path('teacher/questions/add/', teacher_question_form, name='teacher_question_add'),
    path('teacher/questions/<int:question_id>/edit/', teacher_question_form, name='teacher_question_edit'),
    # Legacy/compatibility names (so you never get NoReverseMatch)
    path('teacher/questions/add/', teacher_question_form, name='teacher_add_question'),
    path('teacher/questions/<int:question_id>/edit/', teacher_question_form, name='teacher_edit_question'),
    # Delete (only one needed)
    path('teacher/questions/<int:question_id>/delete/', views.teacher_delete_question, name='teacher_delete_question'),

    # Teacher: Assessment Management
    path('teacher/assessments/', views.teacher_assessment_list, name='teacher_assessment_list'),
    path('teacher/assessments/add/', views.teacher_add_assessment, name='teacher_add_assessment'),
    path('teacher/assessments/<int:assessment_id>/edit/', views.teacher_edit_assessment, name='teacher_edit_assessment'),
    path('teacher/assessments/<int:assessment_id>/delete/', views.teacher_delete_assessment, name='teacher_delete_assessment'),

    # Teacher: Group Management
    path('teacher/groups/', views.teacher_group_list, name='teacher_group_list'),
    path('teacher/groups/add/', views.teacher_add_group, name='teacher_add_group'),
    path('teacher/groups/<int:group_id>/edit/', views.teacher_edit_group, name='teacher_edit_group'),
    path('teacher/groups/<int:group_id>/delete/', views.teacher_delete_group, name='teacher_delete_group'),

    # Miscellaneous
    path('bulk-user-upload/', views.bulk_user_upload, name='bulk_user_upload'),
    path('reset_submissions/', views.reset_submissions_admin, name='reset_submissions_admin'),
    path('teacher/quiz/bulk_upload/', views.teacher_bulk_upload_mcq, name='teacher_bulk_upload_mcq'),

    # Quiz
    path('quiz/<int:quiz_id>/take/', views.take_quiz, name='take_quiz'),
    path('quiz/result/<int:submission_id>/', views.quiz_result, name='quiz_result'),
    path('assessment/<int:assessment_id>/quiz/', views.assessment_quiz, name='assessment_quiz'),
    path('assessments/<int:assessment_id>/quiz-leaderboard/', views.quiz_leaderboard, name='quiz_leaderboard'),

    # Teacher: Quiz Management (duplicates removed, one of each only)
    path('teacher/quizzes/', views.teacher_quiz_list, name='teacher_quiz_list'),
    path('teacher/quizzes/create/', views.teacher_quiz_create, name='teacher_quiz_create'),
    path('teacher/quizzes/<int:quiz_id>/edit/', views.teacher_quiz_edit, name='teacher_quiz_edit'),
    path('teacher/quizzes/<int:quiz_id>/delete/', views.teacher_quiz_delete, name='teacher_quiz_delete'),

    # Notes
    path('notes/', views.notes_list, name='notes_list'),
    path('notes/add/', views.add_note, name='add_note'),
    path('notes/<int:note_id>/edit/', views.edit_note, name='edit_note'),
    path('notes/<int:note_id>/delete/', views.delete_note, name='delete_note'),

    # Notices
    path('notices/', notice_list, name='notice_list'),
    path('notices/add/', add_notice, name='add_notice'),
    path('notices/<int:pk>/', notice_detail, name='notice_detail'),
    path('notices/<int:pk>/edit/', edit_notice, name='edit_notice'),
    path('notices/<int:pk>/delete/', delete_notice, name='delete_notice'),

    # Profile and Bulk MCQ Upload
    path('profile/edit/', edit_profile, name='edit_profile'),
    path('bulk-mcq-upload/', bulk_mcq_upload, name='bulk_mcq_upload'),

    #Courses Links
    path('courses/', views.course_list, name='course_list'),
    path('courses/<int:pk>/', views.course_detail, name='course_detail'),
    path('courses/create/', views.create_course, name='create_course'),
    path('courses/manage/', views.manage_courses, name='manage_courses'),
    path('courses/<int:pk>/edit/', views.edit_course, name='edit_course'),
    path('courses/<int:pk>/delete/', views.delete_course, name='delete_course'),
    path("ckeditor-upload/", ckeditor_upload, name="ckeditor_upload"),
    path('run-code/', views.run_code_view, name="run_code"),
    #student performance
    path('teacher/student-performance/', views.student_performance_list, name='student_performance_list'),
    path('teacher/student-performance/<int:student_id>/', student_performance_detail, name='student_performance_detail'),
    path('teacher/student-performance/export/', views.export_student_performance, name='export_student_performance'),
    path('modules/<int:module_id>/mark-completed/', views.mark_module_completed, name='mark_module_completed'),

]
