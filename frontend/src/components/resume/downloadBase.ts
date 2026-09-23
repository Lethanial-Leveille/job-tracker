import { getBaseResume, renderResume } from "../../lib/api";
import type { ResumeTrack } from "./shell";

// Fetch one flavour of the general resume and write it to disk.
//
// Two calls rather than one because of a rule worth keeping: the server derives
// the base resume from the master and renders through the SAME endpoint a
// tailored resume uses, so the two can never disagree about format. A shortcut
// that produced the PDF in one step would be a second render path, and a second
// render path is how a base resume quietly stops matching a tailored one.
//
// Renders what is SAVED, not what is on screen. The derivation happens on the
// server from the stored master, so unsaved edits are not in it — which is why
// the caller disables this while there are any.
export async function downloadBaseResume(track: ResumeTrack): Promise<void> {
  const base = await getBaseResume(track);
  const { blob, filename } = await renderResume(base);

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
