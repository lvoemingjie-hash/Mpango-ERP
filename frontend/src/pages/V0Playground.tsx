import React from 'react';
import { V0Component } from '../components/v0/V0Component';

export const V0Playground: React.FC = () => {
  const handleCodeGenerated = (code: string) => {
    console.log('Generated code:', code);
    // You can add logic here to handle the generated code
    // For example, save it to state, send to backend, etc.
  };

  return (
    <div className="container mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">V0 AI Playground</h1>
        <p className="text-gray-600">
          Generate React components using Vercel's V0 AI. Describe what you want in natural language and get working TypeScript code.
        </p>
      </div>
      
      <V0Component onCodeGenerated={handleCodeGenerated} />
      
      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-4 bg-blue-50 rounded-lg">
          <h3 className="font-semibold mb-2 text-blue-900">💡 Pro Tips:</h3>
          <ul className="list-disc list-inside space-y-1 text-sm text-blue-800">
            <li>Be specific about styling (Tailwind, CSS, etc.)</li>
            <li>Include interaction details (hover, click, focus states)</li>
            <li>Specify TypeScript interfaces if needed</li>
            <li>Describe responsive behavior</li>
          </ul>
        </div>
        
        <div className="p-4 bg-green-50 rounded-lg">
          <h3 className="font-semibold mb-2 text-green-900">🚀 Getting Started:</h3>
          <ol className="list-decimal list-inside space-y-1 text-sm text-green-800">
            <li>Click a sample prompt or write your own</li>
            <li>Click "Generate Component"</li>
            <li>Copy the generated code</li>
            <li>Use it in your ERP components</li>
          </ol>
        </div>
      </div>
    </div>
  );
};
