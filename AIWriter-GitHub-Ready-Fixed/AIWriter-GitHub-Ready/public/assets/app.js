
/* AIWriter Pro front-end enhancements */
(function () {
  'use strict';

  // ---- Workspace sidebar collapse / restore ----
  var sidebarToggle = document.getElementById('sidebar-toggle');
  var appShell = document.querySelector('.app-shell');

  if (sidebarToggle && appShell) {
    var savedSidebarState = null;

    try {
      savedSidebarState = window.localStorage.getItem(
        'aiwriter-sidebar-collapsed'
      );
    } catch (e) {}

    if (savedSidebarState === 'true') {
      appShell.classList.add('sidebar-collapsed');
    }

    var mainWrap = appShell.querySelector('.app-main-wrap');
    var desktopSidebar = window.matchMedia('(min-width: 851px)');

    // Desktop par collapsed sidebar ke baad dashboard ko
    // remaining full-width column mein shift karo.
    function applySidebarLayout() {
      var collapsed = appShell.classList.contains('sidebar-collapsed');

      if (!mainWrap) return;

      if (collapsed && desktopSidebar.matches) {
        appShell.style.setProperty(
          'grid-template-columns',
          'minmax(0, 1fr)',
          'important'
        );

        mainWrap.style.setProperty('grid-column', '1', 'important');
        mainWrap.style.setProperty('width', '100%', 'important');
        mainWrap.style.setProperty('min-width', '0', 'important');
        mainWrap.style.setProperty('max-width', '100%', 'important');
      } else {
        // Expanded ya mobile layout mein overrides hata do.
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

    updateSidebarButton();

    sidebarToggle.addEventListener('click', function () {
      appShell.classList.toggle('sidebar-collapsed');

      try {
        window.localStorage.setItem(
          'aiwriter-sidebar-collapsed',
          appShell.classList.contains('sidebar-collapsed')
            ? 'true'
            : 'false'
        );
      } catch (e) {}

      updateSidebarButton();
    });

    // Mobile breakpoint cross hone par layout reset rakho.
    if (desktopSidebar.addEventListener) {
      desktopSidebar.addEventListener(
        'change',
        applySidebarLayout
      );
    } else if (desktopSidebar.addListener) {
      desktopSidebar.addListener(applySidebarLayout);
    }
  }

  // ---- Mobile navigation ----
  var toggle = document.getElementById('nav-toggle');
  var nav = document.getElementById('site-nav');

  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');

      toggle.setAttribute(
        'aria-expanded',
        open ? 'true' : 'false'
      );
    });
  }

  // ---- Loading state + duplicate-submit protection ----
  function submitButtons(form) {
    var inside = Array.prototype.slice.call(
      form.querySelectorAll('button[type="submit"]')
    );

    if (form.id) {
      var outside = document.querySelectorAll(
        'button[type="submit"][form="' + form.id + '"]'
      );

      inside = inside.concat(
        Array.prototype.slice.call(outside)
      );
    }

    return inside;
  }

  function setBusy(form, busy) {
    form.dataset.submitting = busy ? 'true' : 'false';

    if (busy) {
      form.setAttribute('aria-busy', 'true');
    } else {
      form.removeAttribute('aria-busy');
    }

    submitButtons(form).forEach(function (button) {
      button.disabled = busy;
      button.classList.toggle('is-loading', busy);
    });

    var status = document.getElementById('generate-status');

    if (status && form.id === 'generate-form') {
      status.textContent = busy
        ? 'Generating your text. This can take several seconds…'
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

        window.setTimeout(function () {
          setBusy(form, true);
        }, 0);
      });

      window.addEventListener('pageshow', function () {
        setBusy(form, false);
      });
    }
  );

  // ---- Prompt character counter ----
  var prompt = document.getElementById('prompt');
  var counter = document.getElementById('prompt-count');

  if (prompt && counter) {
    var max =
      counter.getAttribute('data-max') ||
      prompt.getAttribute('maxlength');

    var update = function () {
      counter.textContent = prompt.value.length + ' / ' + max;
    };

    prompt.addEventListener('input', update);
    update();
  }

  // ---- Copy to clipboard ----
  function fallbackCopy(text) {
    var area = document.createElement('textarea');

    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';

    document.body.appendChild(area);
    area.select();

    var ok = false;

    try {
      ok = document.execCommand('copy');
    } catch (e) {
      ok = false;
    }

    document.body.removeChild(area);
    return ok;
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

        var done = function (ok) {
          if (status) {
            status.textContent = ok
              ? 'Copied to clipboard.'
              : 'Copy failed. Select the text and copy it manually.';
          }

          window.setTimeout(function () {
            if (status) status.textContent = '';
          }, 3000);
        };

        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(
            function () {
              done(true);
            },
            function () {
              done(fallbackCopy(text));
            }
          );
        } else {
          done(fallbackCopy(text));
        }
      });
    }
  );

  // ---- Resend-code cooldown ----
  var resend = document.getElementById('resend-btn');
  var note = document.getElementById('resend-note');

  if (resend) {
    var remaining = parseInt(
      resend.getAttribute('data-cooldown') || '0',
      10
    );

    if (remaining > 0) {
      resend.disabled = true;

      var tick = function () {
        if (remaining <= 0) {
          resend.disabled = false;
          if (note) note.textContent = '';
          return;
        }

        if (note) {
          note.textContent =
            'You can request another code in ' +
            remaining +
            ' seconds.';
        }

        remaining -= 1;
        window.setTimeout(tick, 1000);
      };

      tick();
    }
  }
}());
