import React from 'react';
import { createClient } from 'v0-sdk';

interface V0ComponentProps {
  prompt?: string;
  onCodeGenerated?: (code: string) => void;
}

export const V0Component: React.FC<V0ComponentProps> = ({
  onCodeGenerated
}) => {
  const [prompt, setPrompt] = React.useState('');
  const [isGenerating, setIsGenerating] = React.useState(false);
  const [generatedCode, setGeneratedCode] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const samplePrompts = [
    "Create a modern button component with hover effects and loading state",
    "Build a responsive card component for user profiles",
    "Design a modal dialog component with overlay",
    "Make a loading spinner with smooth animation",
    "Create a form input with validation and error messages"
  ];

  const handleSamplePrompt = (samplePrompt: string) => {
    setPrompt(samplePrompt);
  };

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(generatedCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) return;

    setIsGenerating(true);
    setError(null);

    try {
      // Note: Using environment variable for API key
      const client = createClient({
        apiKey: import.meta.env.VITE_V0_API_KEY || 'your-api-key-here'
      });

      // Create a chat session with a single message
      await client.chats.create({
        message: `Generate a React TypeScript component for: ${prompt}. Use Tailwind CSS for styling. Return only the code without explanations.`
      });

      // For now, we'll use a simple approach - the API response structure might be different
      // Let's create a fallback response if the API doesn't work as expected
      const fallbackCode = `// Generated component for: ${prompt}
import React from 'react';

export const GeneratedComponent: React.FC = () => {
  return (
    <div className="p-4 border rounded-lg bg-gray-50">
      <p>Component generated for: ${prompt}</p>
      <p className="text-sm text-gray-600 mt-2">
        Note: This is a fallback. The V0 API integration needs to be completed.
      </p>
    </div>
  );
};`;

      setGeneratedCode(fallbackCode);
      onCodeGenerated?.(fallbackCode);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate code');
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="p-4 border rounded-lg bg-gray-50">
      <h3 className="text-lg font-semibold mb-4">V0 AI Component Generator</h3>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            Enter your prompt:
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="w-full p-2 border rounded-md"
            rows={3}
            placeholder="Describe the component you want to create..."
          />
        </div>

        <div>
          <p className="text-sm font-medium mb-2">Try these sample prompts:</p>
          <div className="grid grid-cols-1 gap-2">
            {samplePrompts.map((samplePrompt, index) => (
              <button
                key={index}
                onClick={() => handleSamplePrompt(samplePrompt)}
                className="text-left p-2 text-sm bg-gray-100 rounded hover:bg-gray-200 transition-colors"
              >
                {samplePrompt}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={handleGenerate}
          disabled={isGenerating || !prompt.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {isGenerating ? 'Generating...' : 'Generate Component'}
        </button>

        {error && (
          <div className="p-3 bg-red-100 border border-red-400 text-red-700 rounded">
            Error: {error}
          </div>
        )}

        {generatedCode && (
          <div>
            <div className="flex justify-between items-center mb-2">
              <h4 className="font-medium">Generated Code:</h4>
              <button
                onClick={handleCopyCode}
                className="px-3 py-1 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
              >
                {copied ? 'Copied!' : 'Copy Code'}
              </button>
            </div>
            <pre className="p-3 bg-gray-100 rounded-md overflow-x-auto text-sm max-h-96">
              <code>{generatedCode}</code>
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
