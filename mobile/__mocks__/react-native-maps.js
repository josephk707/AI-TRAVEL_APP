// Manual mock for the node module (react-native-maps is a native module
// with no JS-only implementation Jest can run) — a __mocks__ directory
// adjacent to node_modules is applied automatically, no explicit
// jest.mock() call needed, same mechanism as
// __mocks__/react-native-safe-area-context.js.
//
// Renders as plain react-native Views/Text so component tests can assert
// on props (region, markers) and simulate failure via onError, without
// needing an actual native map renderer — which is untestable in Jest
// regardless (no device/simulator), see docs/PHASE_STATUS.md's Phase 5
// Known Limitations.
const React = require("react");
const { View } = require("react-native");

function MapView(props) {
  return React.createElement(View, { testID: props.testID ?? "map-view", ...props }, props.children);
}

function Marker(props) {
  return React.createElement(View, { testID: props.testID ?? "map-marker", ...props });
}

module.exports = {
  __esModule: true,
  default: MapView,
  MapView,
  Marker,
  PROVIDER_GOOGLE: "google",
  PROVIDER_DEFAULT: "default",
};
