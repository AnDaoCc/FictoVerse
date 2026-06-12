/**

 * 帮助问号：单一顶层 portal，避免侧栏 overflow 裁剪与滚动重定位抖动。

 */

(function () {

  let portal = null;

  let activeTip = null;



  const ensurePortal = () => {

    if (portal) return portal;

    portal = document.createElement("div");

    portal.id = "help-tip-portal";

    portal.className = "help-tip-portal";

    portal.hidden = true;

    portal.setAttribute("role", "tooltip");

    document.body.appendChild(portal);

    return portal;

  };



  const hidePortal = () => {

    if (!portal) return;

    portal.hidden = true;

    activeTip = null;

  };



  const showPortal = (tip) => {

    const source = tip.querySelector(".help-tip-bubble");

    if (!source) return;



    const node = ensurePortal();

    node.textContent = source.textContent;

    node.hidden = false;

    activeTip = tip;



    const rect = tip.getBoundingClientRect();

    node.style.left = `${rect.left + rect.width / 2}px`;

    node.style.top = `${rect.top}px`;

    node.classList.remove("help-tip-portal--below");



    const bubbleRect = node.getBoundingClientRect();

    if (bubbleRect.top < 8) {

      node.classList.add("help-tip-portal--below");

      node.style.top = `${rect.bottom}px`;

    }

  };



  const onPointerOver = (event) => {

    const tip = event.target.closest(".help-tip");

    if (!tip || tip === activeTip) return;

    showPortal(tip);

  };



  const onPointerOut = (event) => {

    const tip = event.target.closest(".help-tip");

    if (!tip || tip !== activeTip) return;

    const next = event.relatedTarget;

    if (next && tip.contains(next)) return;

    hidePortal();

  };



  const onFocusIn = (event) => {

    const tip = event.target.closest(".help-tip");

    if (tip) showPortal(tip);

  };



  const onFocusOut = (event) => {

    const tip = event.target.closest(".help-tip");

    if (tip && tip === activeTip) hidePortal();

  };



  document.addEventListener("pointerover", onPointerOver);

  document.addEventListener("pointerout", onPointerOut);

  document.addEventListener("focusin", onFocusIn);

  document.addEventListener("focusout", onFocusOut);

  document.addEventListener("scroll", hidePortal, true);

})();


