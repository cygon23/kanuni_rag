export function RecentQuestions({
  questions,
  onSelect,
  onClear,
}: {
  questions: string[];
  onSelect: (question: string) => void;
  onClear: () => void;
}) {
  if (questions.length === 0) return null;

  return (
    <div className="mt-8">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
          Recent questions
        </h2>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-neutral-500 hover:underline dark:text-neutral-500"
        >
          Clear
        </button>
      </div>
      <ul className="mt-2 space-y-1">
        {questions.map((question) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => onSelect(question)}
              className="w-full truncate rounded-md px-2 py-1.5 text-left text-sm text-neutral-700 hover:bg-neutral-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 dark:text-neutral-300 dark:hover:bg-neutral-900"
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
