# quoteGEN-AI

AI-assisted quotation generator with a React frontend and FastAPI backend.

## Deploy

The repository includes a Netlify build configuration (`netlify.toml`) and a
Render Blueprint (`render.yaml`). Connect the GitHub repository to Netlify to
publish the frontend. In Render, create a Blueprint instance from this
repository and set the prompted environment variables before deploying:

- `GEMINI_API_KEY`: Gemini API key used by the backend.
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service-role key. Keep this secret and
  enter it only in Render's environment settings; never put it in the repository
  or frontend configuration.
- `CORS_ORIGINS`: exact Netlify site origin, such as
  `https://your-site.netlify.app`.

The Supabase URL and frontend publishable key are configured in `netlify.toml`.
After Render deploys, set the Netlify environment variable `VITE_API_URL` to
the Render service URL (for example, `https://quotegen-api.onrender.com`) and
trigger a new deploy. Set Supabase's Site URL and allowed redirect URL to the
exact Netlify URL in the Supabase Auth URL settings.

The Render API uses Supabase Auth to verify bearer access tokens. User data is
scoped to the authenticated Supabase user when backend Supabase credentials
are configured.
