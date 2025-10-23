// in frontend/src/pages/ProblemListPage.tsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom'; // Import Link for navigation

interface Question {
  id: number;
  title: string;
  // You can add 'difficulty' or other fields here later
}

const ProblemListPage = () => {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    axios.get('http://localhost:8000/api/questions/', { withCredentials: true })
      .then(response => {
        setQuestions(response.data);
      })
      .catch(error => {
        console.error("There was an error fetching the questions!", error);
        setError("Failed to load questions.");
      });
  }, []);

  if (error) {
    return <div style={{ color: 'red' }}>{error}</div>;
  }

  return (
    <div style={{ padding: '20px' }}>
      <h1>Problem Set</h1>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #333' }}>
            <th style={{ padding: '10px', textAlign: 'left' }}>#</th>
            <th style={{ padding: '10px', textAlign: 'left' }}>Title</th>
          </tr>
        </thead>
        <tbody>
          {questions.map((question) => (
            <tr key={question.id} style={{ borderBottom: '1px solid #ccc' }}>
              <td style={{ padding: '10px' }}>{question.id}</td>
              <td style={{ padding: '10px' }}>
                <Link to={`/problems/${question.id}`} style={{ textDecoration: 'none', color: '#007bff' }}>
                  {question.title}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ProblemListPage;