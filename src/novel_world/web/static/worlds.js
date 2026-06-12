document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".book-front-delete").forEach((form) => {
    form.addEventListener("click", (e) => e.stopPropagation());
  });
});
