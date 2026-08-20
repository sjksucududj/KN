import { useEffect, useState } from "react";
import ConfirmModal from "./ConfirmModal";
import { subscribeConfirm, settleConfirm } from "../services/confirmService";

/**
 * ConfirmHost — satu-satunya tempat dialog konfirmasi dirender (FASE P5).
 *
 * Dipasang sekali di `index.js` bersebelahan dengan `<Toaster/>`. Dengan begitu
 * `askConfirm()/askReason()/askText()` bisa dipanggil dari **mana pun** — termasuk dari
 * hook & service yang bukan komponen — tanpa setiap layar menambah state & JSX sendiri.
 *
 * Kenapa bukan satu <ConfirmModal> per layar? Karena itulah sebabnya 21 tempat memilih
 * `window.confirm`: menambah 3 state + 1 blok JSX hanya untuk bertanya "yakin?" terasa
 * mahal, jadi orang mengambil jalan pintas yang memblokir peramban. Standar hanya
 * dipatuhi kalau ia lebih murah daripada jalan pintasnya.
 */
export default function ConfirmHost() {
  const [req, setReq] = useState(null);

  useEffect(() => subscribeConfirm(setReq), []);

  const o = req?.opts || {};

  return (
    <ConfirmModal
      open={!!req}
      title={o.title || "Konfirmasi"}
      message={o.message}
      confirmLabel={o.confirmLabel}
      cancelLabel={o.cancelLabel}
      danger={o.danger}
      withReason={!!o.withReason}
      reasonLabel={o.reasonLabel}
      reasonRequired={o.reasonRequired !== false}
      reasonPlaceholder={o.reasonPlaceholder}
      inputType={o.inputType}
      choices={o.choices}
      testId={o.testId || "confirm-modal"}
      // Kontrak nilai: lihat services/confirmService.js.
      //  · mode alasan   → string alasan (batal = null)
      //  · mode pilihan  → string kunci pilihan (batal = null)
      //  · mode Ya/Batal → true / false
      onChoose={(key) => settleConfirm(String(key))}
      onConfirm={(reason) => settleConfirm(o.withReason ? String(reason ?? "") : true)}
      onCancel={() => settleConfirm(
        (o.withReason || (Array.isArray(o.choices) && o.choices.length > 0)) ? null : false)}
    />
  );
}
