
/* AIWriter Pro - Main JavaScript */
(function () {
  'use strict';

  // ==========================================
  // 1. SIDEBAR COLLAPSE / EXPAND
  // ==========================================

  var sidebarToggle = document.getElementById('sidebar-toggle');
  var appShell = document.querySelector('.app-frame');

  if (sidebarToggle && appShell) {
    var mainWrap = appShell.querySelector('.app-main-wrap');
    var desktopSidebar = window.matchMedia('(min-width: 851px)');

    // Restore saved sidebar state
    try {
      if (
        localStorage.getItem('aiwriter-sidebar-collapsed') === 'true'
      ) {
        appShell.classList.add('sidebar-collapsed');
      }
    } catch (error) {}

    // IMPORTANT: Fix desktop grid when sidebar is hidden
    function applySidebarLayout() {
      if (!mainWrap) return;

      var collapsed = appShell.classList.contains(
        'sidebar-collapsed'
      );

      if (collapsed && desktopSidebar.matches) {
        appShell.style.setProperty(
          'grid-template-columns',
          'minmax(0, 1fr)',
          'important'
        );

        mainWrap.style.setProperty(
          'grid-column',
          '1',
          'important'
        );

        mainWrap.style.setProperty('width', '100%', 'important');
        mainWrap.style.setProperty('min-width', '0', 'important');
        mainWrap.style.setProperty('max-width', '100%', 'important');

      } else {
        appShell.style.removeProperty('grid-template-columns');
        mainWrap.style.removeProperty('grid-column');
        mainWrap.style.removeProperty('width');
        mainWrap.style.removeProperty('min-width');
        mainWrap.style.removeProperty('max-width');
      }
    }

    function updateSidebarButton() {
      var collapsed = appShell.classList.contains(
        'sidebar-collapsed'
      );

      sidebarToggle.setAttribute(
        'aria-expanded',
        collapsed ? 'false' : 'true'
      );

      sidebarToggle.setAttribute(
        'aria-label',
        collapsed ? 'Show sidebar' : 'Hide sidebar'
      );

      sidebarToggle.setAttribute(
        'title',
        collapsed ? 'Show sidebar' : 'Hide sidebar'
      );

      var label = sidebarToggle.querySelector(
        '.sidebar-toggle-label'
      );

      if (label) {
        label.textContent = collapsed
          ? 'Show sidebar'
          : 'Hide sidebar';
      }

      applySidebarLayout();
    }

    // Apply saved state on page load
    updateSidebarButton();

    // Toggle sidebar
    sidebarToggle.addEventListener('click', function () {
      appShell.classList.toggle('sidebar-collapsed');

      try {
        localStorage.setItem(
          'aiwriter-sidebar-collapsed',
          appShell.classList.contains('sidebar-collapsed')
            ? 'true'
            : 'false'
        );
      } catch (error) {}

      updateSidebarButton();
    });

    // Handle screen resizing
    if (desktopSidebar.addEventListener) {
      desktopSidebar.addEventListener(
        'change',
        applySidebarLayout
      );
    } else if (desktopSidebar.addListener) {
      desktopSidebar.addListener(applySidebarLayout);
    }

    window.addEventListener('resize', applySidebarLayout);
  }

  // ==========================================
  // 2. MOBILE NAVIGATION
  // ==========================================

  var navToggle = document.getElementById('nav-toggle');
  var nav = document.getElementById('site-nav');

  if (navToggle && nav) {
    navToggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');

      navToggle.setAttribute(
        'aria-expanded',
        open ? 'true' : 'false'
      );
    });
  }

  // ==========================================
  // 3. FORM LOADING STATE
  // ==========================================

  function getSubmitButtons(form) {
    var buttons = Array.from(
      form.querySelectorAll('button[type="submit"]')
    );

    if (form.id) {
      var externalButtons = document.querySelectorAll(
        'button[type="submit"][form="' + form.id + '"]'
      );

      buttons = buttons.concat(Array.from(externalButtons));
    }

    return buttons;
  }

  function setFormBusy(form, busy) {
    form.dataset.submitting = busy ? 'true' : 'false';

    if (busy) {
      form.setAttribute('aria-busy', 'true');
    } else {
      form.removeAttribute('aria-busy');
    }

    getSubmitButtons(form).forEach(function (button) {
      button.disabled = busy;
      button.classList.toggle('is-loading', busy);
    });

    var status = document.getElementById('generate-status');

    if (status && form.id === 'generate-form') {
      status.textContent = busy
        ? 'Generating your text. Please wait...'
        : '';
    }
  }

  document.querySelectorAll('form[data-loading-form]').forEach(
    function (form) {
      form.addEventListener('submit', function (event) {
        if (form.dataset.submitting === 'true') {
          event.preventDefault();
          return;
        }

        setFormBusy(form, true);
      });
    }
  );

  // Restore form buttons when returning to the page
  window.addEventListener('pageshow', function () {
    document.querySelectorAll('form[data-loading-form]').forEach(
      function (form) {
        setFormBusy(form, false);
      }
    );
  });

  // ==========================================
  // 4. PROMPT CHARACTER COUNTER
  // ==========================================

  var prompt = document.getElementById('prompt');
  var counter = document.getElementById('prompt-count');

  if (prompt && counter) {
    var max =
      counter.getAttribute('data-max') ||
      prompt.getAttribute('maxlength') ||
      '';

    function updateCounter() {
      counter.textContent = prompt.value.length + ' / ' + max;
    }

    prompt.addEventListener('input', updateCounter);
    updateCounter();
  }

  // ==========================================
  // 5. COPY GENERATED CONTENT
  // ==========================================

  function fallbackCopy(text) {
    var area = document.createElement('textarea');

    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';

    document.body.appendChild(area);
    area.select();

    var success = false;

    try {
      success = document.execCommand('copy');
    } catch (error) {
      success = false;
    }

    document.body.removeChild(area);
    return success;
  }

  document.querySelectorAll('[data-copy-target]').forEach(
    function (button) {
      button.addEventListener('click', function () {
        var target = document.querySelector(
          button.getAttribute('data-copy-target')
        );

        var status = document.getElementById('copy-status');

        if (!target) return;

        var text = target.innerText;

        function showResult(success) {
          if (status) {
            status.textContent = success
              ? 'Copied to clipboard!'
              : 'Copy failed. Please copy manually.';
          }

          window.setTimeout(function () {
            if (status) status.textContent = '';
          }, 3000);
        }

        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(
            function () {
              showResult(true);
            },
            function () {
              showResult(fallbackCopy(text));
            }
          );
        } else {
          showResult(fallbackCopy(text));
        }
      });
    }
  );

  // ==========================================
  // 6. RESEND OTP COOLDOWN
  // ==========================================

  var resend = document.getElementById('resend-btn');
  var resendNote = document.getElementById('resend-note');

  if (resend) {
    var remaining = parseInt(
      resend.getAttribute('data-cooldown') || '0',
      10
    );

    if (remaining > 0) {
      resend.disabled = true;

      function countdown() {
        if (remaining <= 0) {
          resend.disabled = false;

          if (resendNote) {
            resendNote.textContent = '';
          }

          return;
        }

        if (resendNote) {
          resendNote.textContent =
            'You can request another code in ' +
            remaining +
            ' seconds.';
        }

        remaining--;
        window.setTimeout(countdown, 1000);
      }

      countdown();
    }
  }


  // ==========================================
  // 7. QUICK-START PROMPT IDEAS
  // ==========================================

  document.querySelectorAll('[data-prompt-starter]').forEach(function (button) {
    button.addEventListener('click', function () {
      var promptField = document.getElementById('prompt');
      var typeField = document.getElementById('writing_type');
      var sample = button.getAttribute('data-prompt') || '';
      var writingType = button.getAttribute('data-writing-type') || '';

      if (!promptField) return;
      if (typeField && writingType) {
        typeField.value = writingType;
        typeField.dispatchEvent(new Event('change', { bubbles: true }));
      }
      promptField.value = sample;
      promptField.dispatchEvent(new Event('input', { bubbles: true }));
      promptField.focus();
      promptField.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  // ==========================================
  // 8. DOWNLOAD A GENERATED DRAFT
  // ==========================================

  document.querySelectorAll('[data-download-target]').forEach(function (button) {
    button.addEventListener('click', function () {
      var selector = button.getAttribute('data-download-target');
      var target = selector ? document.querySelector(selector) : null;
      var status = document.getElementById('download-status');
      if (!target) return;

      try {
        var blob = new Blob([target.innerText], { type: 'text/plain;charset=utf-8' });
        var objectUrl = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = objectUrl;
        link.download = 'aiwriter-draft.txt';
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 1000);
        if (status) status.textContent = 'Your draft download has started.';
      } catch (error) {
        if (status) status.textContent = 'Download failed. Please copy the draft instead.';
      }
    });
  });


  // ==========================================
  // PADDLE CHECKOUT INTEGRATION
  // ==========================================

  var paddleConfig = document.getElementById('paddle-checkout-config');
  var paddleButtons = document.querySelectorAll('.paddle-checkout-button');

  if (paddleConfig && paddleButtons.length) {
    var paddleStatus = document.getElementById('paddle-status');
    var paddleToken = paddleConfig.getAttribute('data-token') || '';
    var paddleEnvironment = paddleConfig.getAttribute('data-environment') || '';
    var checkoutReference = paddleConfig.getAttribute('data-checkout-ref') || '';
    var customerEmail = paddleConfig.getAttribute('data-customer-email') || '';
    var paddleSdkPromise = null;
    var paddleInitialized = false;
    var activeCheckoutButton = null;
    var checkoutOpened = false;

    function paddleMessage(message) {
      if (paddleStatus) paddleStatus.textContent = message;
    }

    function setCheckoutBusy(button, busy) {
      if (!button) return;
      button.disabled = busy;
      if (busy) {
        button.setAttribute('aria-busy', 'true');
      } else {
        button.removeAttribute('aria-busy');
      }
    }

    function releaseCheckoutButton() {
      setCheckoutBusy(activeCheckoutButton, false);
      activeCheckoutButton = null;
    }

    function eventReason(event) {
      var data = event && event.data ? event.data : {};
      var detail = data.detail || data.message || data.code || '';
      return typeof detail === 'string' ? detail.slice(0, 220) : '';
    }

    function loadPaddleSdk() {
      if (window.Paddle) return Promise.resolve(window.Paddle);
      if (paddleSdkPromise) return paddleSdkPromise;

      paddleSdkPromise = new Promise(function (resolve, reject) {
        var script = document.createElement('script');
        var settled = false;
        var timeoutId = window.setTimeout(function () {
          if (settled) return;
          settled = true;
          reject(new Error('paddle_sdk_timeout'));
        }, 15000);

        function finish(error) {
          if (settled) return;
          settled = true;
          window.clearTimeout(timeoutId);
          if (error || !window.Paddle) {
            reject(error || new Error('paddle_sdk_unavailable'));
          } else {
            resolve(window.Paddle);
          }
        }

        script.id = 'paddle-sdk-dynamic';
        script.async = true;
        script.src = 'https://cdn.paddle.com/paddle/v2/paddle.js';
        script.onload = function () { finish(); };
        script.onerror = function () { finish(new Error('paddle_sdk_blocked')); };
        document.head.appendChild(script);
      }).catch(function (error) {
        paddleSdkPromise = null;
        var failedScript = document.getElementById('paddle-sdk-dynamic');
        if (failedScript && failedScript.parentNode) {
          failedScript.parentNode.removeChild(failedScript);
        }
        throw error;
      });

      return paddleSdkPromise;
    }

    function initializePaddle() {
      if (paddleInitialized) return Promise.resolve(window.Paddle);
      if (!paddleToken || !checkoutReference) {
        return Promise.reject(new Error('billing_config_incomplete'));
      }

      if (paddleEnvironment === 'production' && paddleToken.indexOf('live_') !== 0) {
        return Promise.reject(new Error('live_client_token_required'));
      }
      if (paddleEnvironment === 'sandbox' && paddleToken.indexOf('test_') !== 0) {
        return Promise.reject(new Error('sandbox_client_token_required'));
      }

      return loadPaddleSdk().then(function (paddle) {
        if (paddleInitialized) return paddle;

        if (paddleEnvironment === 'sandbox') {
          paddle.Environment.set('sandbox');
        }

        paddle.Initialize({
          token: paddleToken,
          eventCallback: function (event) {
            if (!event || !event.name) return;

            if (event.name === 'checkout.opened' || event.name === 'checkout.loaded') {
              checkoutOpened = true;
              paddleMessage('Secure checkout is opening.');
            } else if (event.name === 'checkout.completed') {
              paddleMessage('Payment submitted. Your plan will update after Paddle confirms the subscription.');
              releaseCheckoutButton();
            } else if (event.name === 'checkout.closed') {
              paddleMessage('Checkout closed. You can reopen it whenever you are ready.');
              checkoutOpened = false;
              releaseCheckoutButton();
            } else if (event.name === 'checkout.warning') {
              var warning = eventReason(event);
              console.warn('[AIWriter Paddle] checkout.warning', event.data || {});
              paddleMessage(warning
                ? 'Paddle checkout warning: ' + warning
                : 'Paddle reported a checkout warning. Check your Live checkout settings.');
            } else if (event.name === 'checkout.error') {
              var reason = eventReason(event);
              console.error('[AIWriter Paddle] checkout.error', event.data || {});
              paddleMessage(reason
                ? 'Paddle could not open checkout: ' + reason
                : 'Paddle rejected this checkout. Check domain approval, default payment link, token, and price ID.');
              checkoutOpened = false;
              releaseCheckoutButton();
            }
          }
        });

        paddleInitialized = true;
        return paddle;
      });
    }

    function openPaddleCheckout(button) {
      var priceId = button.getAttribute('data-price-id') || '';
      var planName = button.getAttribute('data-plan-name') || 'plan';

      if (priceId.indexOf('pri_') !== 0) {
        paddleMessage('The ' + planName + ' plan does not have a valid Paddle Price ID.');
        return;
      }

      if (button.disabled) return;
      activeCheckoutButton = button;
      checkoutOpened = false;
      setCheckoutBusy(button, true);
      paddleMessage('Connecting to secure checkout...');

      initializePaddle().then(function (paddle) {
        paddleMessage('Opening secure checkout...');
        try {
          paddle.Checkout.open({
            items: [{ priceId: priceId, quantity: 1 }],
            customData: { aiwriter_checkout_ref: checkoutReference },
            customer: customerEmail ? { email: customerEmail } : undefined,
            settings: { displayMode: 'overlay', theme: 'light' }
          });

          window.setTimeout(function () {
            if (activeCheckoutButton === button && !checkoutOpened) {
              paddleMessage('Checkout has not confirmed opening. Please retry; check the browser console for Paddle details.');
              releaseCheckoutButton();
            }
          }, 20000);
        } catch (error) {
          console.error('[AIWriter Paddle] Checkout.open failed', error);
          paddleMessage('Checkout could not start. Please retry. ' + (error && error.message ? error.message : ''));
          releaseCheckoutButton();
        }
      }).catch(function (error) {
        console.error('[AIWriter Paddle] Initialization failed', error);
        var message = error && error.message ? error.message : 'unknown_error';
        if (message === 'live_client_token_required') {
          paddleMessage('Live checkout is misconfigured: PADDLE_CLIENT_TOKEN must start with live_.');
        } else if (message === 'sandbox_client_token_required') {
          paddleMessage('Sandbox checkout is misconfigured: PADDLE_CLIENT_TOKEN must start with test_.');
        } else if (message === 'billing_config_incomplete') {
          paddleMessage('Checkout configuration is incomplete. Check the Live token and signed-in session.');
        } else if (message === 'paddle_sdk_blocked' || message === 'paddle_sdk_timeout') {
          paddleMessage('Paddle secure checkout could not load. Check your connection or browser content blockers.');
        } else {
          paddleMessage('Paddle could not initialize: ' + message.slice(0, 180));
        }
        releaseCheckoutButton();
      });
    }

    paddleButtons.forEach(function (button) {
      button.addEventListener('click', function () {
        openPaddleCheckout(button);
      });
    });

    // Warm up Paddle in the background while the customer reads the plans.
    paddleMessage('Preparing secure checkout...');
    initializePaddle().then(function () {
      paddleMessage('Secure checkout is ready.');
    }).catch(function (error) {
      console.error('[AIWriter Paddle] Background initialization failed', error);
      var message = error && error.message ? error.message : 'unknown_error';
      if (message === 'live_client_token_required') {
        paddleMessage('Live checkout is misconfigured: PADDLE_CLIENT_TOKEN must start with live_.');
      } else if (message === 'sandbox_client_token_required') {
        paddleMessage('Sandbox checkout is misconfigured: PADDLE_CLIENT_TOKEN must start with test_.');
      } else if (message === 'paddle_sdk_blocked' || message === 'paddle_sdk_timeout') {
        paddleMessage('Paddle could not load. Your plan buttons will retry when clicked.');
      } else {
        paddleMessage('Paddle setup needs attention: ' + message.slice(0, 180));
      }
    });
  }

})();