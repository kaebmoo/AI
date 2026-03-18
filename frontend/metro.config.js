const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");
const path = require("path");

const config = getDefaultConfig(__dirname);

// Ensure .mjs files can be resolved (needed for tslib.es6.mjs)
if (!config.resolver.sourceExts.includes("mjs")) {
  config.resolver.sourceExts.push("mjs");
}

// Fix: tslib CJS module has no "default" export → zrender/echarts crash on web.
// Intercept tslib resolution to use ES module version (has `export default`).
const originalResolveRequest = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === "tslib" && platform === "web") {
    return {
      type: "sourceFile",
      filePath: path.resolve(__dirname, "node_modules/tslib/tslib.es6.mjs"),
    };
  }
  if (originalResolveRequest) {
    return originalResolveRequest(context, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = withNativeWind(config, { input: "./global.css" });
