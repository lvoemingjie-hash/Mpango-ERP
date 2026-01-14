import React from 'react';
import { V0Component } from './V0Component';

export const V0Test: React.FC = () => {
  const handleCodeGenerated = (code: string) => {
    console.log('V0 generated code:', code);
    // You can save this to a file or display it in the UI
  };

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">V0 AI Test</h2>
      
      <div className="mb-6">
        <h3 className="text-lg font-semibold mb-2">Try these sample prompts:</h3>
        <ul className="list-disc list-inside space-y-1 text-sm text-gray-600">
          <li>"Create a simple button component with hover effects"</li>
          <li>"Build a login form with email and password fields"</li>
          <li>"Design a card component for displaying user profiles"</li>
          <li>"Make a loading spinner component"</li>
        </ul>
      </div>

      <V0Component onCodeGenerated={handleCodeGenerated} />
    </div>
  );
};
