document.addEventListener("DOMContentLoaded", () => {
  const prompt = document.querySelector("#prompt");
  const count = document.querySelector("#char-count");
  const form = document.querySelector("#generate-form");
  if (prompt && count) {
    const updateCount = () => { count.textContent = String(prompt.value.length); };
    updateCount();
    prompt.addEventListener("input", updateCount);
  }
  if (form) {
    form.addEventListener("submit", () => {
      const button = form.querySelector(".generate-button");
      if (button) {
        button.disabled = true;
        const label = button.querySelector(".button-label");
        const loading = button.querySelector(".button-loading");
        if (label) label.hidden = true;
        if (loading) loading.hidden = false;
      }
    });
  }
  async function copyText(text, button) {
    try {
      await navigator.clipboard.writeText(text);
      const old = button.textContent;
      button.textContent = "Copied!";
      window.setTimeout(() => { button.textContent = old; }, 1400);
    } catch (_) {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      button.textContent = "Copied!";
    }
  }
  const copy = document.querySelector("#copy-result");
  if (copy) copy.addEventListener("click", () => {
    const target = document.getElementById(copy.dataset.copyTarget);
    if (target) copyText(target.textContent, copy);
  });
  document.querySelectorAll(".copy-history").forEach(button => {
    button.addEventListener("click", () => {
      const item = button.closest(".history-item");
      const output = item && item.querySelector("pre");
      if (output) copyText(output.textContent, button);
    });
  });
});