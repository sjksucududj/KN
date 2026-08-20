// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }

      // Suppress benign "Failed to parse source map" warnings from 3rd-party
      // packages (mis. @zxing/browser yang merujuk file .ts yang tidak ikut di-publish).
      webpackConfig.ignoreWarnings = [
        ...(webpackConfig.ignoreWarnings || []),
        /Failed to parse source map/,
      ];
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // webpack-dev-server v5 removed onBeforeSetupMiddleware/onAfterSetupMiddleware
  // (react-scripts/CRA still injects them → schema validation crash). Translate them
  // into the v5-compatible `setupMiddlewares` hook so CRA dev middleware keeps working.
  const beforeMw = devServerConfig.onBeforeSetupMiddleware;
  const afterMw = devServerConfig.onAfterSetupMiddleware;
  delete devServerConfig.onBeforeSetupMiddleware;
  delete devServerConfig.onAfterSetupMiddleware;

  // v5 removed the `https`/`http2` keys (replaced by `server`). CRA still sets `https`.
  if ("https" in devServerConfig) {
    const httpsVal = devServerConfig.https;
    delete devServerConfig.https;
    if (httpsVal) {
      devServerConfig.server =
        typeof httpsVal === "object"
          ? { type: "https", options: httpsVal }
          : { type: "https" };
    }
  }
  if ("http2" in devServerConfig) delete devServerConfig.http2;

  const originalSetupMiddlewares = devServerConfig.setupMiddlewares;
  devServerConfig.setupMiddlewares = (middlewares, devServer) => {
    if (typeof beforeMw === "function") beforeMw(devServer);
    if (typeof originalSetupMiddlewares === "function") {
      middlewares = originalSetupMiddlewares(middlewares, devServer);
    }
    // Setup health endpoints if enabled
    if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
      setupHealthEndpoints(devServer, healthPluginInstance);
    }
    if (typeof afterMw === "function") afterMw(devServer);
    return middlewares;
  };

  return devServerConfig;
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

module.exports = webpackConfig;
