export default function Spinner({ size = 5 }) {
  return (
    <div className={`w-${size} h-${size} border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin`} />
  )
}
