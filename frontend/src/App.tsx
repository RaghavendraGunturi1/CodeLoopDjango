// in frontend/src/App.tsx
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import ProblemListPage from './pages/ProblemListPage';
import ProblemPage from './pages/ProblemPage';
import './App.css';

function App() {
  return (
    <Router>
      <div className="App">
        <Routes>
          <Route path="/" element={<ProblemListPage />} />
          <Route path="/problems" element={<ProblemListPage />} />
          <Route path="/problems/:questionId" element={<ProblemPage />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;