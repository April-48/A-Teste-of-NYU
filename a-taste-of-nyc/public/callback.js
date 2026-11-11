/* Public export: route interactions to states evaluated by the Python callback.
 * Only selection routing happens here; statistics and figures come from Python.
 */
(() => {
  const base = JSON.parse(document.getElementById("_dash-config").textContent).requests_pathname_prefix;
  const version = document.querySelector('meta[name="public-version"]').content;
  // Dash expects extensionless bootstrap routes. Static hosts reliably infer
  // JSON MIME types from .json, so adapt only these two same-origin GETs.
  const nativeFetch = window.fetch.bind(window);
  window.fetch = function(input, options) {
    const url = new URL(typeof input === "string" ? input : input.url || input.href, location.href);
    if (url.origin === location.origin && [base + "_dash-layout", base + "_dash-dependencies"].includes(url.pathname)) {
      url.pathname += ".json";
      url.searchParams.set("v", version);
      return nativeFetch(input instanceof Request ? new Request(url, input) : url, options);
    }
    return nativeFetch(input, options);
  };
  const cache = new Map();
  let revision = 0;
  function json(url) {
    url = base + url.replace(/^\//, "") + "?v=" + version;
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
      update: async function(borough, heatClick, resetClicks, barClick, scatterClick, minimum, cuisineFocus, countFilter, selected) {
        const turn = ++revision;
        const trigger = (window.dash_clientside.callback_context.triggered[0]?.prop_id || "").split(".")[0];
        const manifest = await json("/state-index.json");
        const unchanged = () => manifest.outputs.map(() => window.dash_clientside.no_update);
        try {
          if (trigger === "reset") {
            borough = "All NYC"; selected = null; minimum = 1; countFilter = "all";
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
          countFilter = Object.hasOwn(manifest.count_ranges, countFilter) ? countFilter : "all";
          const range = manifest.count_ranges[countFilter];
          const count = manifest.counts[bi][selected] || 0;
          if (countFilter !== "all" && selected && (count < range[1] || (range[2] !== null && count > range[2]))) {
            if (trigger === "heatmap") countFilter = "all";
            else selected = null;
          }
          const ci = Math.max(0, manifest.cuisines.indexOf(selected ?? null));
          const ri = Object.keys(manifest.count_ranges).indexOf(countFilter);
          minimum = manifest.minimums.includes(minimum) ? minimum : 1;
          const packed = await json(`/states/${bi}-${ci}-${minimum}-${ri}.json`);
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
