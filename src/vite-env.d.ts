/// <reference types="vite/client" />

// Optional: extend the env types for stricter checks
interface ImportMetaEnv {
  readonly VITE_SUPABASE_URL: string
  readonly VITE_SUPABASE_ANON_KEY: string
  // add other VITE_* vars here as needed
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

