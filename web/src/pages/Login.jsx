export default function Login({ error }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg)] px-6">
      <div className="w-full max-w-sm">
        <div className="bg-card border border-theme rounded-2xl p-8 text-center shadow-sm">
          <div className="text-2xl font-bold text-body mb-1">Job Search</div>
          <div className="text-sm text-muted mb-8">Santiago Aldana · Executive Search</div>

          {error && (
            <div className="mb-4 text-xs text-red-500 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
              {error === 'unauthorized' ? 'Access denied — this app is private.' : `Auth error: ${error}`}
            </div>
          )}

          <a
            href="/auth/login"
            className="flex items-center justify-center gap-3 w-full bg-white dark:bg-slate-700 border border-theme hover:border-blue-400 rounded-xl py-3 px-4 text-sm font-medium text-body transition-colors shadow-sm"
          >
            <svg width="18" height="18" viewBox="0 0 48 48">
              <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
              <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
              <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
              <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
            </svg>
            Sign in with Google
          </a>

          <p className="text-xs text-faint mt-4">
            Uses your Google passkey — no password needed
          </p>
        </div>
      </div>
    </div>
  )
}
