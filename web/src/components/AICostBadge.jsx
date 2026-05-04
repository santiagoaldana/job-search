/**
 * Shows model name and estimated cost next to any button that calls the Claude API.
 * Usage: <AICostBadge model="opus" cost="$0.05" />
 *        <AICostBadge model="haiku" cost="$0.002" />
 */
export default function AICostBadge({ model = 'haiku', cost }) {
  const isOpus = model === 'opus'
  const color = isOpus
    ? 'bg-violet-50 text-violet-600 border-violet-200 dark:bg-violet-900/30 dark:text-violet-300 dark:border-violet-700'
    : 'bg-sky-50 text-sky-600 border-sky-200 dark:bg-sky-900/30 dark:text-sky-300 dark:border-sky-700'

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border ${color}`}
      title={`Uses Claude ${isOpus ? 'Opus (most capable)' : 'Haiku (fast + cheap)'}. Estimated cost: ~${cost}`}
    >
      <span>AI</span>
      <span className="opacity-60">·</span>
      <span>~{cost}</span>
    </span>
  )
}
