export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Method not allowed." });
  }
  const { topic = "Can", message, history = [] } = req.body || {};
  if (typeof message !== "string" || !message.trim() || message.length > 1500) {
    return res.status(400).json({ error: "Please send a short answer (up to 1500 characters)." });
  }
  if (!process.env.GROQ_API_KEY) {
    return res.status(503).json({
      error: "AI key is not connected yet. Add GROQ_API_KEY in Vercel → Project Settings → Environment Variables, then redeploy."
    });
  }
  const safeHistory = Array.isArray(history)
    ? history.slice(-10).filter(m => m && ["user", "assistant"].includes(m.role) && typeof m.content === "string").map(m => ({ role: m.role, content: m.content.slice(0, 1500) }))
    : [];
  const system = `You are English Buddy, a patient and encouraging English teacher for a beginner learner in Pakistan. Teach in very simple English and Roman Urdu when useful. Current lesson: ${String(topic).slice(0, 40)}. Correct the learner's sentence gently. Always show: (1) Correct sentence, (2) short reason in simple Roman Urdu, (3) one new easy practice question. If their answer is already correct, praise them and still give one next question. Keep replies concise and friendly. For CAN, teach can + base verb, ability and permission. Never shame the learner.`;
  try {
    const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { "Authorization": `Bearer ${process.env.GROQ_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        messages: [{ role: "system", content: system }, ...safeHistory, { role: "user", content: message.trim() }],
        temperature: 0.4,
        max_tokens: 450
      })
    });
    const data = await response.json();
    if (!response.ok) {
      console.error("Groq API error:", data);
      return res.status(502).json({ error: "The AI service could not answer. Check your API key and try again." });
    }
    const reply = data.choices?.[0]?.message?.content;
    if (!reply) return res.status(502).json({ error: "The AI returned an empty answer. Please try again." });
    return res.status(200).json({ reply });
  } catch (error) {
    console.error("Tutor request failed:", error);
    return res.status(500).json({ error: "Something went wrong. Please try again." });
  }
}