# English Buddy AI

A mobile-friendly English practice tutor for beginner learners. It includes guided lessons for Can, Could, May, Might, Must, daily conversation, sentence correction, Roman Urdu explanations, translation prompts, and quizzes.

## Deploy on Vercel

This app is a static HTML page plus a Vercel Node.js function.

1. Import this GitHub repository into Vercel.
2. Set **Root Directory** to `English-Buddy-AI`.
3. Add the environment variable `GROQ_API_KEY` in Project Settings → Environment Variables.
4. Redeploy the project.

Get an API key from https://console.groq.com/keys. Keep the key only in Vercel Environment Variables. Never put it in `index.html` or commit it to GitHub.

## Local preview

Use a Vercel-compatible local environment and run `vercel dev` from this directory. The AI endpoint requires `GROQ_API_KEY`.

Without the key, the interface loads but AI replies are disabled and the page explains how to connect the key.
