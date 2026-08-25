// Polyfills required by @supabase/supabase-js's PKCE auth flow on React
// Native (no browser/Node globals exist there). MUST be imported before
// anything else — including transitively, before any other module gets a
// chance to touch `crypto`/`URL` — which is why this sits at the very top
// of the actual app entry point rather than inside src/lib/supabase.ts.
import 'react-native-get-random-values';
import 'react-native-url-polyfill/auto';

import { registerRootComponent } from 'expo';

import App from './App';

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
// It also ensures that whether you load the app in Expo Go or in a native build,
// the environment is set up appropriately
registerRootComponent(App);
