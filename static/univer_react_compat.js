/* Univer UMD compatibility for React 18 global builds.
   Some Univer builds expect React 19 JSX-runtime functions on global React. */
(function () {
  "use strict";
  if (!window.React || !window.ReactDOM) return;
  if (!window.React.jsx) {
    const jsx = function (type, props, key) {
      const values = Object.assign({}, props);
      if (key !== undefined) values.key = key;
      return window.React.createElement(type, values);
    };
    window.React.jsx = jsx;
    window.React.jsxs = jsx;
  }
  window.ReactJSXRuntime ||= {
    jsx: window.React.jsx, jsxs: window.React.jsxs,
    Fragment: window.React.Fragment
  };
})();
