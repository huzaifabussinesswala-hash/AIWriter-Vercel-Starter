document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy-target]");
  if (!button) return;
  const target = document.getElementById(button.dataset.copyTarget);
  if (!target) return;
  const original = button.textContent;
  try {
    await navigator.clipboard.writeText(target.innerText || target.textContent || "");
    button.textContent = "Copied!";
    setTimeout(() => { button.textContent = original; }, 1400);
  } catch {
    button.textContent = "Select and copy";
    setTimeout(() => { button.textContent = original; }, 1800);
  }
});

document.addEventListener("submit", (event) => {
  const button = event.target.querySelector("#generate-btn");
  if (button) {
    button.disabled = true;
    button.textContent = "Generating…";
  }
});
