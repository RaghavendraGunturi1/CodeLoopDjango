// in frontend/src/components/CodeEditor.tsx
import React from 'react';
import Editor from '@monaco-editor/react';

const CodeEditor = () => {
  return (
    <Editor
      height="70vh"
      defaultLanguage="python"
      defaultValue="# Write your code here"
      theme="vs-dark"
    />
  );
};

export default CodeEditor;