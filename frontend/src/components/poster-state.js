// The poster as last kept by the user, or the generated design if nothing was kept yet.
export const keptPoster = (editor) => structuredClone(editor.saved ?? { layers: editor.layers, scrim: editor.scrim });
export const sameConfig = (a, b) => JSON.stringify(a) === JSON.stringify(b);
