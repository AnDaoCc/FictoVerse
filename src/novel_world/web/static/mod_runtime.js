(function () {
  const registry = {};

  function sortFns(name) {
    const items = registry[name] || [];
    return items.slice().sort((a, b) => (a.priority || 100) - (b.priority || 100));
  }

  window.NovelWorldMods = {
    registerHook(name, fn, options) {
      if (!name || typeof fn !== "function") return;
      const priority = options && typeof options.priority === "number" ? options.priority : 100;
      if (!registry[name]) registry[name] = [];
      registry[name].push({ fn, priority });
    },

    runHooks(name, value, context) {
      let result = value;
      const ctx = context || {};
      sortFns(name).forEach(({ fn }) => {
        try {
          const out = fn(result, ctx);
          if (out !== undefined && out !== null) result = out;
        } catch (_err) {
          /* ignore MOD errors */
        }
      });
      return result;
    },

    listHooks() {
      return Object.keys(registry).reduce((acc, key) => {
        acc[key] = (registry[key] || []).length;
        return acc;
      }, {});
    },
  };
})();
