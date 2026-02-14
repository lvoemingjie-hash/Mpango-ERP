const variants: Record<string, string> = {
  green: 'bg-green-50 text-green-700 ring-green-600/20',
  gray: 'bg-gray-50 text-gray-600 ring-gray-500/10',
  red: 'bg-red-50 text-red-700 ring-red-600/10',
  blue: 'bg-blue-50 text-blue-700 ring-blue-700/10',
  yellow: 'bg-yellow-50 text-yellow-800 ring-yellow-600/20',
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: keyof typeof variants;
}

export function Badge({ children, variant = 'gray' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset ${variants[variant] ?? variants.gray}`}
    >
      {children}
    </span>
  );
}
