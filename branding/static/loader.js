/* Sign-in with a UserID instead of an email address.
   The chat software only knows email addresses, so a UserID such as
   "desert-fox" is stored as "desert-fox@mirah.local". People type only the
   UserID; this adds the rest when they press Sign in or Create Account.
   Anything that already contains "@" (the admin's login) is left alone.
   Loaded by the chat software on every page from /static/loader.js. */
(function () {
  'use strict';

  var DOMAIN = '@mirah.local';
  var LABEL = 'UserID';
  var PLACEHOLDER = 'Enter your UserID, for example desert-fox';
  var NAME_PLACEHOLDER = 'A display name, not your real name';

  function emailField() {
    return document.querySelector('#auth-container input#email');
  }

  function toAddress(value) {
    var text = value.trim();
    return text && text.indexOf('@') === -1 ? text + DOMAIN : text;
  }

  function setText(element, text) {
    if (element && element.textContent !== text) element.textContent = text;
  }

  function setAttribute(element, name, value) {
    if (element && element.getAttribute(name) !== value) element.setAttribute(name, value);
  }

  // The page redraws itself (switching between sign in and sign up), so this
  // runs again whenever it changes, and only writes what differs.
  function relabel() {
    var input = emailField();
    if (!input) return;
    setText(document.querySelector('#auth-container label[for="email"]'), LABEL);
    setAttribute(input, 'placeholder', PLACEHOLDER);
    setAttribute(input, 'aria-label', LABEL);
    setAttribute(input, 'autocomplete', 'username');
    setAttribute(input, 'inputmode', 'text');
    setAttribute(input, 'autocapitalize', 'none');
    setAttribute(input, 'spellcheck', 'false');
    setAttribute(document.querySelector('#auth-container input[autocomplete="name"]'), 'placeholder', NAME_PLACEHOLDER);
  }

  // Runs before the page's own sign-in code, which then reads the full address.
  function completeAddress(event) {
    var input = emailField();
    if (!input || !event.target.contains(input)) return;
    var address = toAddress(input.value);
    if (address === input.value) return;
    input.value = address;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  document.addEventListener('submit', completeAddress, true);
  new MutationObserver(relabel).observe(document.documentElement, { childList: true, subtree: true });
  relabel();
})();
