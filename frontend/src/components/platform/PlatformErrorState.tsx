/**
 * PlatformErrorState — displays an error state with retry button.
 *
 * Used when an API call fails. Shows the error message and offers a retry.
 */
interface PlatformErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function PlatformErrorState({ message, onRetry }: PlatformErrorStateProps) {
  return (
    <div className="flex items-center justify-center rounded-lg border border-red-200 bg-red-50 p-6">
      <div className="text-center">
        <svg
          className="mx-auto h-8 w-8 text-red-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
          />
        </svg>
        <p className="mt-2 text-sm text-red-700">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-red-700 shadow-sm ring-1 ring-inset ring-red-300 hover:bg-red-50"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}
