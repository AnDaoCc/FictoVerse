export function initSettingsNav() {
  const layout = document.querySelector(".settings-layout");
  if (!layout) return;

  const navLinks = layout.querySelectorAll(".settings-nav__link");
  const groups = layout.querySelectorAll(".settings-group[id]");
  if (!navLinks.length || !groups.length) return;

  const setActive = (id) => {
    navLinks.forEach((link) => {
      link.classList.toggle("active", link.getAttribute("href") === `#${id}`);
    });
  };

  navLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const href = link.getAttribute("href");
      if (!href || !href.startsWith("#")) return;
      const target = document.querySelector(href);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      setActive(href.slice(1));
      history.replaceState(null, "", href);
    });
  });

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible?.target?.id) setActive(visible.target.id);
    },
    { rootMargin: "-20% 0px -55% 0px", threshold: [0, 0.25, 0.5] },
  );

  groups.forEach((g) => observer.observe(g));

  const hash = location.hash.replace("#", "");
  if (hash) setActive(hash);
}
