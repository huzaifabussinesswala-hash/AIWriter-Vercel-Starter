const form = document.querySelector("#writer-form");
const topicInput = document.querySelector("#topic");
const button = document.querySelector("#generate-btn");
const resultWrap = document.querySelector("#result-wrap");
const result = document.querySelector("#result");
const statusBox = document.querySelector("#status");
const copyButton = document.querySelector("#copy-btn");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const topic = topicInput.value.trim();
  if (!topic) { topicInput.focus(); return; }
  resultWrap.hidden = false;
  result.textContent = "";
  statusBox.className = "status";
  statusBox.textContent = "Draft tayyar ho raha hai...";
  button.disabled = true;
  button.innerHTML = "<span>✦</span> Generating...";
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        topic,
        content_type: document.querySelector("#content-type").value,
        tone: document.querySelector("#tone").value,
        length: document.querySelector("#length").value
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Generation fail ho gayi.");
    result.textContent = data.result;
    statusBox.textContent = "Draft ready — publish karne se pehle review kar lein.";
  } catch (error) {
    statusBox.className = "status error";
    statusBox.textContent = error.message || "Request fail hui. Dobara try karein.";
  } finally {
    button.disabled = false;
    button.innerHTML = "<span>✦</span> Generate content <span class='arrow'>↗</span>";
  }
});
copyButton.addEventListener("click", async () => {
  if (!result.textContent.trim()) return;
  try {
    await navigator.clipboard.writeText(result.textContent);
    copyButton.textContent = "Copied!";
    setTimeout(() => copyButton.textContent = "Copy text", 1400);
  } catch {
    statusBox.className = "status error";
    statusBox.textContent = "Copy nahi hua. Text select karke manually copy karein.";
  }
});
