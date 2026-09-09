import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import './ds/styles.css';
import './app.css';
import App from './App.jsx';
import Design from './screens/Design.jsx';

// `#design` mounts the component bench instead of the reader — every element on one
// page, in both registers, talking to no API. It is a hash rather than a screen inside
// the app so the reader gains no route, no button and no way to wander into it.
const bench = window.location.hash === '#design';

createRoot(document.getElementById('root')).render(
  <StrictMode>{bench ? <Design /> : <App />}</StrictMode>,
);
