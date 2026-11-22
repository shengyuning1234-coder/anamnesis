const APP_PREFIX = document.querySelector('meta[name="app-prefix"]')?.content || '';
function appURL(path) {
  return typeof path === 'string' && path.startsWith('/') && !path.startsWith('//') && !path.startsWith(APP_PREFIX + '/') ? APP_PREFIX + path : path;
}
