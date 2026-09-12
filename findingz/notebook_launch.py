"""Save before navigating the current tab; no popup or new-window dependency."""
import streamlit as st

JS = """
const pendingKey = Symbol.for('findingz.notebookNavigation.pending');
const pending = window[pendingKey] || (window[pendingKey] = new Set());
export default function(component) {
    const {data, parentElement, setTriggerValue} = component;
    const status = parentElement.querySelector('[role="status"]');
    const buttons = [...parentElement.querySelectorAll('button')];
    const reply = data.reply;
    if (reply && pending.has(reply.id)) {
        pending.delete(reply.id);
        if (reply.error) {
            status.textContent = reply.error;
        } else if (reply.url) {
            status.textContent = 'Notebook saved. Going to JupyterLab…';
            window.location.assign(reply.url);
        } else {
            status.textContent = 'Notebook saved. Use the saved path or recovery link below.';
        }
    }
    buttons.forEach(button => {
        button.disabled = pending.size > 0 || (button.dataset.mode === 'current' && !data.enabled);
        button.onclick = () => {
            const id = crypto.randomUUID();
            pending.add(id);
            buttons.forEach(item => item.disabled = true);
            status.textContent = 'Saving notebook…';
            setTriggerValue('request', {id, mode: button.dataset.mode});
        };
    });
}
"""
launch_buttons = st.components.v2.component(
    "findingz_notebook_launch",
    html='<div class="actions"><button data-mode="current">Continue current analysis in Jupyter</button>'
         '<button data-mode="blank">Start from blank template</button></div><p role="status"></p>',
    css="""
    .actions {display:flex; gap:1rem; flex-wrap:wrap}
    button {font:inherit; color:var(--st-text-color); background:var(--st-background-color);
      border:1px solid var(--st-border-color, #888); border-radius:.5rem; padding:.5rem .8rem; cursor:pointer}
    button:hover {border-color:var(--st-primary-color)}
    button:disabled {opacity:.5; cursor:default}
    p {font:inherit; font-size:.875rem}
    """,
    js=JS,
)
