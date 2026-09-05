export const THEME_KEY = "focos-theme";

/** Page background per palette; also the browser chrome colour when installed. */
export const PAGE_COLORS = { dark: "#13141c", light: "#f2efe4" } as const;

/** Sets data-theme and the theme-color meta for a resolved theme. Shared by the boot script and the toggle. */
export const APPLY_THEME_JS = `function focosApplyTheme(t){document.documentElement.dataset.theme=t;var c=t==="dark"?${JSON.stringify(PAGE_COLORS.dark)}:${JSON.stringify(PAGE_COLORS.light)};var ms=document.querySelectorAll('meta[name="theme-color"]');for(var i=0;i<ms.length;i++){ms[i].setAttribute("content",c)}}`;

/** Runs before first paint so the page never flashes the wrong theme. */
export const THEME_SCRIPT = `(function(){${APPLY_THEME_JS};try{var k=${JSON.stringify(THEME_KEY)},t=localStorage.getItem(k);if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}focosApplyTheme(t)}catch(e){}})();`;

export function applyTheme(resolved: "dark" | "light") {
  document.documentElement.dataset.theme = resolved;
  const c = PAGE_COLORS[resolved];
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", c));
}
