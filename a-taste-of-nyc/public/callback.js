/* Public export: route interactions to states evaluated by the Python callback.
 * Only selection routing happens here; statistics and figures come from Python.
 */
(() => {
  const cache = new Map();
  let revision = 0;
  function json(url) {
    if (!cache.has(url)) {
      cache.set(url, fetch(url).then(response => {
        if (!response.ok) throw new Error(`Unable to load ${url}: ${response.status}`);
        return response.json();
      }).catch(error => { cache.delete(url); throw error; }));
    }
    return cache.get(url);
  }
  async function unpack(value) {
    if (value && typeof value === "object" && value.$object) {
      const object = structuredClone(await json(`/objects/${value.$object}.json`));
      if (object.layout && object.layout.template) {
        object.layout.template = await unpack(object.layout.template);
      }
      return object;
    }
    return value;
  }
  window.dash_clientside = Object.assign({}, window.dash_clientside, {
    nyc_public: {
      update: async function(borough, heatClick, resetClicks, barClick, scatterClick, minimum, cuisineFocus, selected) {
        const turn = ++revision;
        const trigger = (window.dash_clientside.callback_context.triggered[0]?.prop_id || "").split(".")[0];
        const manifest = await json("/state-index.json");
        const unchanged = () => manifest.outputs.map(() => window.dash_clientside.no_update);
        try {
          if (trigger === "reset") {
            borough = "All NYC"; selected = null; minimum = 1;
          } else if (trigger === "cuisine-focus") {
            selected = cuisineFocus;
          } else if (trigger === "heatmap" && heatClick?.points?.length) {
            const p = heatClick.points[0];
            if (manifest.boroughs.includes(p.y) && manifest.cuisines.includes(p.x)) {
              borough = p.y; selected = p.x;
            }
          } else if (trigger === "bar" || trigger === "scatter") {
            const p = (trigger === "bar" ? barClick : scatterClick)?.points?.[0];
            const cuisine = p?.customdata?.[0] ?? (trigger === "bar" ? p?.y : null);
            if (manifest.cuisines.includes(cuisine)) selected = cuisine;
          }
          const bi = Math.max(0, manifest.boroughs.indexOf(borough));
          const ci = Math.max(0, manifest.cuisines.indexOf(selected ?? null));
          minimum = manifest.minimums.includes(minimum) ? minimum : 1;
          const packed = await json(`/states/${bi}-${ci}-${minimum}.json`);
          const output = await Promise.all(packed.map(unpack));
          return turn === revision ? output : unchanged();
        } catch (error) {
          console.error(error);
          if (turn !== revision) return unchanged();
          const output = unchanged();
          const message = manifest.outputs.findIndex(o => o.id === "sample-status");
          output[message] = "Could not load this selection. Please retry or refresh the page.";
          return output;
        }
      }
    }
  });
})();
