// Manual mock for the node module, per Jest's convention (a __mocks__
// directory adjacent to node_modules is applied automatically for node
// module mocks, no explicit jest.mock() call needed).
//
// react-native-safe-area-context ships its own jest mock
// (react-native-safe-area-context/jest/mock), but it only has an ES
// `export default {...}` — no named exports. This project's Babel/TS
// config compiles named imports (`import { useSafeAreaInsets } from
// "react-native-safe-area-context"`) to direct property access on the
// required module object, which never unwraps `.default` the way a
// namespace import (`import * as X`) does. Re-exporting the mock's
// default object as this module's own `module.exports` makes
// useSafeAreaInsets/useSafeAreaFrame/SafeAreaProvider/initialWindowMetrics
// resolve correctly for both named and namespace imports.
module.exports = require("react-native-safe-area-context/jest/mock").default;
