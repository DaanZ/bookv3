import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import './ds/styles.css';
import './app.css';
import App from './App.jsx';
import Design from './screens/Design.jsx';
import Print from './screens/Print.jsx';

// Two hashes mount something other than the reader. Both are hashes rather than screens
// inside the app for the same reason: the reader gains no route to wander into, and the
// URL is a thing you can send somebody.
//
//   #design        the component bench — every element, both registers, no API
//   #print/<key>   one book laid out for paper, to print or save as a PDF
//
// The key is URL-encoded, because a book key is a filename stem and filename stems in
// this library contain commas, ampersands and apostrophes.
const hash = window.location.hash;
const printing = hash.startsWith('#print/') ? decodeURIComponent(hash.slice('#print/'.length)) : null;

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {hash === '#design' ? <Design /> : printing ? <Print bookKey={printing} /> : <App />}
  </StrictMode>,
);
