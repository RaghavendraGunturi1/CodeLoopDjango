// in frontend/src/pages/ProblemPage.tsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Editor from '@monaco-editor/react';

// (The Question interface remains the same)
interface Question {
  id: number;
  title: string;
  description: string;
}

const ProblemPage = () => {
  const [question, setQuestion] = useState<Question | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 1. Add new state to hold the code from the editor
  const [code, setCode] = useState<string>("# Write your Python code here");

  useEffect(() => {
    const questionId = 1;
    axios.get(`http://127.0.0.1:8000/api/questions/${questionId}/`)
      .then(response => setQuestion(response.data))
      .catch(error => {
        console.error("Error fetching question!", error);
        setError("Failed to load question.");
      });
  }, []);

  // 2. This function will be called when the user clicks the submit button
  const handleSubmit = async () => {
    if (!question) return;

    try {
      // We will create this '/api/submit/' endpoint in Django next
      const response = await axios.post('http://127.0.0.1:8000/api/submit/', {
        question_id: question.id,
        code: code,
        language: 'python' // Hardcoding for now
      });
      console.log('Submission Response:', response.data);
      alert('Submission sent successfully!');
    } catch (err) {
      console.error("Submission failed!", err);
      alert('Failed to submit code.');
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      {/* Left side: Problem Description */}
      <div style={{ flex: 1, padding: '20px', overflowY: 'auto' }}>
        {error && <div style={{ color: 'red' }}>{error}</div>}
        {!question && !error && <div>Loading...</div>}
        {question && (
          <>
            <h1>{question.title}</h1>
            <div dangerouslySetInnerHTML={{ __html: question.description }} />
          </>
        )}
      </div>

      {/* Right side: Code Editor and Button */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderLeft: '1px solid #ccc' }}>
        <Editor
          height="90%" // Adjusted height to make space for the button
          defaultLanguage="python"
          defaultValue={code}
          theme="vs-dark"
          // 3. Update the 'code' state whenever the editor content changes
          onChange={(value) => setCode(value || "")}
        />
        {/* 4. Add the submit button */}
        <button
          onClick={handleSubmit}
          style={{ height: '10%', background: '#28a745', color: 'white', border: 'none', fontSize: '1.2rem', cursor: 'pointer' }}
        >
          Submit
        </button>
      </div>
    </div>
  );
};

export default ProblemPage;