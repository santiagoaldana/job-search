export default function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-center justify-between px-4 pt-6 pb-3">
      <div>
        <h1 className="text-xl font-bold text-body">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-0.5">{subtitle}</p>}
      </div>
      {action && <div>{action}</div>}
    </div>
  )
}
