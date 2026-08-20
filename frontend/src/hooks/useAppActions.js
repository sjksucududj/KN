import { useCallback, useEffect, useRef } from "react";
import axios, { API, setAuthToken, setActiveEntity } from "../services/apiClient";
import { defaultViewForRole, defaultNavIdForRole } from "../config/navigationConfig";
import { can } from "../config/roles";
import { formatQty } from "../utils/formatters";
import { blocksOrder, isOrderable, notOrderableReason } from "../utils/lifecycle";
import { askConfirm } from "@/services/confirmService";

/**
 * Business logic / async action hook for the App shell.
 *
 * Accepts all relevant state values + setters and returns a flat object of
 * memoized async action functions. This keeps App.js focused on layout and
 * routing, while all REST orchestration + side-effects live here.
 *
 * NOTE: Keep this hook pure-orchestration only; no JSX, no DOM.
 */
export function useAppActions(state) {
  const {
    user, token, auditFilters, selectedCustomer, selectedAddress, cart, data, selectedEntity,
    setUser, setToken, setActiveView, setNotice, setOnboarding, setShowOnboarding,
    setData, setTemplates, setUoms, setMovements, setTasks, setUsers, setPermissions, setAuditLogs,
    setSelectedCustomer, setSelectedAddress, setSelectedProduct, setBreakdown,
    setCart, setLastDocument, setLastLabel, setPreviewHtml,
    setActiveDetail, setLoading, setEntities, setNotifications, setUnreadCount,
    setSettings, setPaymentTerms, setEntityContext, setSelectedEntity,
    setActiveNavId,   // grouped IA nav highlight sync
  } = state;

  // Helper: query suffix entitas aktif (Multi-Entity Fase 0).
  const entityParam = (selectedEntity && selectedEntity !== "all") ? `?entity_id=${selectedEntity}` : "";
  const entityValue = (selectedEntity && selectedEntity !== "all") ? selectedEntity : "";

  // PERF (Fase 1): ref agar loadAll TIDAK bergantung pada selectedCustomer.
  // Sebelumnya selectedCustomer ada di deps loadAll → tiap pilih customer di POS
  // memicu reload penuh (8-11 API) = sumber lag. Sekarang reload penuh hanya saat
  // login / ganti entitas / ganti role.
  const selectedCustomerRef = useRef(selectedCustomer);
  useEffect(() => { selectedCustomerRef.current = selectedCustomer; }, [selectedCustomer]);

  // FASE F — mode penegakan lifecycle produk yang BERLAKU (dari `/api/rnd/meta`).
  // Dipakai `addToCart` sebagai pagar UX; server tetap penjaga terakhir.
  const rndEnforcementRef = useRef("block");

  // Keep axios auth header in sync with token.
  useEffect(() => {
    setAuthToken(token);
  }, [token]);

  const login = async (email, password) => {
    try {
      const response = await axios.post(`${API}/auth/login`, { email, password });
      setAuthToken(response.data.token);
      setToken(response.data.token);
      // FASE E-8 (E8.1) — IZIN EFEKTIF pengguna ikut disimpan pada objek user supaya
      // layar bisa bertanya `can(currentUser.permissions, "interco", "create")` alih-alih
      // menebak dari literal peran. Tanpa ini, tombol untuk peran baru (Admin Sales /
      // Finance) tetap mati walau server mengizinkan — atau hidup lalu ditolak 403.
      const authedUser = {
        ...response.data.user,
        permissions: response.data.permissions || {},
        role_label: response.data.role_label || response.data.user?.role || "",
      };
      setUser(authedUser);
      localStorage.setItem("kn_token", response.data.token);
      localStorage.setItem("kn_user", JSON.stringify(authedUser));
      // Multi-Entity (F0-B): simpan konteks entitas + tentukan entitas aktif valid.
      const ec = response.data.entity_context || null;
      if (ec) {
        if (setEntityContext) setEntityContext(ec);
        localStorage.setItem("kn_entity_ctx", JSON.stringify(ec));
        if (Array.isArray(ec.entities)) setEntities(ec.entities);
        let def = localStorage.getItem("kn_entity") || "all";
        if (!ec.can_switch_entity) {
          // single-entity (sales/warehouse) terkunci ke home.
          def = ec.home_entity_id || (ec.entities?.[0]?.id) || "all";
        } else if (def !== "all" && !(ec.allowed_entity_ids || []).includes(def)) {
          def = "all";  // bersihkan pilihan basi dari sesi user lain.
        }
        setSelectedEntity?.(def);
        localStorage.setItem("kn_entity", def);
        setActiveEntity(def);
      }
      setActiveView(defaultViewForRole(response.data.user.role));
      if (setActiveNavId) setActiveNavId(defaultNavIdForRole(response.data.user.role));
      setNotice(`Login berhasil sebagai ${authedUser.role_label || authedUser.role}.`);
      try {
        const onbRes = await axios.get(`${API}/onboarding`, { headers: { Authorization: `Bearer ${response.data.token}` } });
        setOnboarding(onbRes.data);
        if (onbRes.data.progress_pct < 100) setShowOnboarding(true);
      } catch (_) {}
    } catch (error) {
      setNotice(error.response?.data?.detail || "Login gagal.");
    }
  };

  const logout = () => {
    setUser(null);
    setToken("");
    localStorage.removeItem("kn_token");
    localStorage.removeItem("kn_user");
    setNotice("Anda sudah logout.");
  };

  const showMetricDetail = (type) => {
    const metric = data.metrics || {};
    const details = {
      products: { title: "Produk Aktif", body: "Klik ini membawa Anda ke Sales POS untuk inspect produk dan stok per gudang.", target: "sales", cta: "Buka Sales POS", facts: [{ label: "Total produk", value: metric.products || 0 }, { label: "Langkah berikutnya", value: "Review katalog & stock breakdown" }] },
      available: { title: "Stok Tersedia", body: "Stok yang masih bisa dijual setelah reserved quantity dikurangi.", target: "sales", cta: "Lihat stok produk", facts: [{ label: "Jml tersedia", value: formatQty(metric.available_qty) }, { label: "Guidance", value: "Prioritaskan item low stock" }] },
      reserved: { title: "Stok Dipesan", body: "Stok yang sedang dibooking oleh sales order dan akan unlock jika expired/cancelled.", target: "orders", cta: "Review orders", facts: [{ label: "Jml dipesan", value: formatQty(metric.reserved_qty) }, { label: "Kontrol", value: "Cek aging & approval" }] },
      orders: { title: "Pesanan Aktif", body: "Order aktif membutuhkan approval, confirmation, WMS fulfillment, atau payment simulation.", target: "orders", cta: "Buka ruang pesanan", facts: [{ label: "Pesanan aktif", value: metric.active_orders || 0 }, { label: "Langkah berikutnya", value: "Approve/confirm jika pending" }] },
      warehouses: { title: "Gudang Aktif", body: "Klik untuk masuk WMS dan melihat struktur gudang, bins, task scan, dan movement ledger.", target: "operations", cta: "Buka WMS", facts: [{ label: "Jumlah gudang", value: metric.warehouses || 0 }, { label: "Guidance", value: "Review task scanner" }] },
    };
    setActiveDetail(details[type]);
    if (["products", "available"].includes(type)) setActiveView("sales");
    if (["reserved", "orders"].includes(type)) setActiveView("orders");
    if (type === "warehouses") setActiveView("operations");
  };

  const loadAll = useCallback(async () => {
    setLoading(true);
    setActiveEntity(selectedEntity || "all");  // pastikan header entitas sinkron
    const eq = (selectedEntity && selectedEntity !== "all") ? `?entity_id=${selectedEntity}` : "";
    try {
      const [dash, tpls, uomResp, entResp, notifResp, unreadResp, setResp, termResp,
             rndResp] = await Promise.all([
        axios.get(`${API}/dashboard${eq}`).catch(() => ({ data: { products: [], customers: [], orders: [], warehouses: [], metrics: {} } })),
        axios.get(`${API}/document-templates`).catch(() => ({ data: [] })),
        axios.get(`${API}/uoms`).catch(() => ({ data: [] })),
        axios.get(`${API}/entities`).catch(() => ({ data: [] })),
        axios.get(`${API}/notifications${eq}`).catch(() => ({ data: [] })),
        axios.get(`${API}/notifications/unread-count${eq}`).catch(() => ({ data: { count: 0 } })),
        axios.get(`${API}/settings/effective${eq}`).catch(() => ({ data: {} })),
        axios.get(`${API}/payment-terms`).catch(() => ({ data: [] })),
        // FASE F — kebijakan lifecycle produk (rnd.lifecycle_enforcement) supaya POS
        // bisa MENANDAI produk yang belum boleh dijual sebelum sales menabrak
        // penolakan server di ujung checkout. Server tetap penjaga terakhir.
        axios.get(`${API}/rnd/meta${eq}`).catch(() => ({ data: { policy: {} } })),
      ]);
      const rndPolicy = rndResp.data?.policy || {};
      rndEnforcementRef.current = String(rndPolicy.lifecycle_enforcement || "block");
      setData({ ...dash.data, rnd_policy: rndPolicy });
      setTemplates(tpls.data);
      setUoms(uomResp.data);
      setEntities(Array.isArray(entResp.data) ? entResp.data : []);
      setNotifications(Array.isArray(notifResp.data) ? notifResp.data : []);
      setUnreadCount(unreadResp.data?.count || 0);
      setSettings(setResp.data || {});
      setPaymentTerms(Array.isArray(termResp.data) ? termResp.data.filter((t) => t.active !== false) : []);

      // FASE E-8 — dulu daftar peran: Admin Sales (izinnya `wms.view` &
      // `inventory.view`) tidak ikut mengambil mutasi/tugas gudang sehingga papan
      // pemantauannya kosong tanpa alasan.
      const myPerms = user?.permissions || {};
      if (can(myPerms, "wms", "view")) {
        const [movResp, taskResp] = await Promise.all([
          axios.get(`${API}/inventory/movements`).catch(() => ({ data: [] })),
          axios.get(`${API}/wms/tasks`).catch(() => ({ data: [] })),
        ]);
        setMovements(movResp.data || []);
        setTasks(Array.isArray(taskResp.data) ? taskResp.data : taskResp.data?.items || []);
      }

      if (can(myPerms, "user", "view")) {
        // FASE F-6 — SATU izin tidak boleh menarik panggilan yang bukan wewenangnya.
        // Keputusan F-2 memberi `manager + user.view` (BACA) supaya kolom "akun tertaut"
        // di layar Karyawan tidak lagi kosong. Efek sampingnya: manajer ikut masuk blok
        // ini lalu memanggil `/permissions` (butuh `permission.view`) & `/audit-logs`
        // (butuh `audit.view`) → DUA 403 di konsol setiap kali beranda dimuat, ditelan
        // `.catch()` menjadi "matriks izin kosong" & "tidak ada jejak audit". Persis
        // kelas "panel mati" yang diaudit F-2: layar diam, orangnya tak pernah tahu.
        // Obatnya sesuai doktrin repo: JANGAN memanggil yang tak boleh dipakai —
        // tiap panggilan dipagari IZINNYA SENDIRI, bukan izin tetangganya.
        const [userResp, permissionResp, auditResp] = await Promise.all([
          axios.get(`${API}/users`).catch(() => ({ data: [] })),
          can(myPerms, "permission", "view")
            ? axios.get(`${API}/permissions`).catch(() => ({ data: { matrix: {}, actions: [] } }))
            : Promise.resolve({ data: { matrix: {}, actions: [] } }),
          can(myPerms, "audit", "view")
            ? axios.get(`${API}/audit-logs`).catch(() => ({ data: [] }))
            : Promise.resolve({ data: [] }),
        ]);
        setUsers(userResp.data || []);
        setPermissions(permissionResp.data || { matrix: {}, actions: [] });
        setAuditLogs(auditResp.data || []);
      }

      if (!selectedCustomerRef.current && dash.data.customers?.[0]) {
        setSelectedCustomer(dash.data.customers[0]);
        setSelectedAddress(dash.data.customers[0].addresses?.[0]?.id || "");
      }
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal mengambil data sistem.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.role, selectedEntity]);

  // Auto-load data once user is authenticated.
  useEffect(() => { if (user) loadAll(); }, [loadAll, user]);

  const inspectProduct = async (product) => {
    setSelectedProduct(product);
    if (!product) return;
    const response = await axios.get(`${API}/products/${product.id}/stock-breakdown`);
    setBreakdown(response.data);
  };

  const addToCart = (product, qty, unit, extra = {}) => {
    // FASE F — barang yang belum sah (masih di alur R&D) TIDAK boleh masuk keranjang.
    // Dicegah di sini supaya sales tahu sejak awal, bukan gagal di ujung checkout.
    if (blocksOrder(product, rndEnforcementRef.current)) {
      setNotice(notOrderableReason(product));
      return;
    }
    if (!isOrderable(product) && String(rndEnforcementRef.current) === "warn") {
      setNotice(`Perhatian: ${notOrderableReason(product)}`);
    }
    // SALES REVAMP V2 — Mode "Beli per Roll": pilih roll spesifik (utuh), qty = Σ panjang roll.
    if (extra && extra.purchase_mode === "roll") {
      const rollLines = extra.roll_lines || [];
      const total = Math.round(rollLines.reduce((s, r) => s + Number(r.take_qty || 0), 0) * 100) / 100;
      setCart((current) => {
        const others = current.filter((item) => item.product.id !== product.id);
        return [...others, {
          product, quantity: total, unit: product.base_unit,
          purchase_mode: "roll", roll_lines: rollLines, rolls_snapshot: extra.rolls_snapshot || [],
        }];
      });
      setNotice(`${product.name} — ${rollLines.length} roll (${total} ${product.base_unit}) masuk keranjang.`);
      return;
    }
    const addQty = Number(qty) > 0 ? Number(qty) : Math.min(10, Math.max(1, product.available_qty || 1));
    const useUnit = unit || product.base_unit;
    setCart((current) => {
      const existing = current.find((item) => item.product.id === product.id);
      if (existing) {
        // baris roll lama diganti dgn baris qty bila user tambah ulang dgn qty biasa
        if (existing.purchase_mode === "roll") {
          return current.map((item) =>
            item.product.id === product.id
              ? { product, quantity: addQty, unit: useUnit }
              : item
          );
        }
        return current.map((item) =>
          item.product.id === product.id
            ? { ...item, quantity: Number(item.quantity || 0) + addQty, unit: useUnit }
            : item
        );
      }
      return [...current, { product, quantity: addQty, unit: useUnit }];
    });
    setNotice(`${product.name} (${addQty} ${useUnit}) masuk keranjang.`);
  };

  const createCustomer = async (form) => {
    if (!form.name || !form.pic_name || !form.phone || !form.city || !form.address) {
      setNotice("Lengkapi data customer baru terlebih dahulu.");
      return;
    }
    try {
      const response = await axios.post(`${API}/customers`, { ...form, entity_id: entityValue });
      setSelectedCustomer(response.data);
      setSelectedAddress(response.data.addresses[0].id);
      setNotice(`Customer ${response.data.name} aktif dan siap dipakai.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal membuat customer.");
    }
  };

  const submitOrder = async (extra = {}) => {
    try {
      const payload = {
        customer_id: selectedCustomer.id,
        shipping_address_id: selectedAddress,
        shipment_policy: "allow_partial_shipment",
        sales_name: "Ayu Marketing",
        entity_id: entityValue,
        order_discount_percent: 0,
        fulfillment_method: extra.fulfillment_method || "kirim",
        pickup_date: extra.pickup_date || "",
        delivery_date: extra.delivery_date || "",
        sales_team: Array.isArray(extra.sales_team) ? extra.sales_team : [],
        payment_term_code: extra.payment_term_code || "",
        allow_backorder: Boolean(extra.allow_backorder),
        confirm_mixed_lot: Boolean(extra.confirm_mixed_lot),
        needs_tax_invoice: Boolean(extra.needs_tax_invoice),
        tax_override: extra.tax_override || "",
        items: cart.map((item) => {
          const sp = (extra.special_prices || {})[item.product.id];
          const base = {
            product_id: item.product.id, quantity: item.quantity, unit: item.unit,
            discount_percent: 0,
            price_approval_id: sp && sp.has_special ? (sp.price_approval_id || "") : "",
          };
          // SALES REVAMP V2 — Beli per Roll: kirim pilihan roll eksplisit.
          if (item.purchase_mode === "roll") {
            return { ...base, purchase_mode: "roll", roll_lines: item.roll_lines || [] };
          }
          return base;
        }),
      };
      const response = await axios.post(`${API}/sales-orders`, payload);
      const o = response.data;
      const tail = o.ppn_amount > 0 ? ` · PPN ${formatQty(o.ppn_amount)}` : "";
      setNotice(`${o.number} dibuat (${o.status.replaceAll("_", " ")})${tail}. Grand total Rp ${formatQty(o.grand_total)}.`);
      setCart([]);
      setActiveView("orders");
      await loadAll();
      return true;
    } catch (error) {
      const detail = error.response?.data?.detail;
      // KN_17 — 409 gate kredit (customer terblokir tanpa override approved)
      if (typeof detail === "object" && detail && detail.code === "CREDIT_BLOCKED") {
        const reasons = (detail.reasons || []).join("; ");
        setNotice(`⛔ ${detail.message}${reasons ? " — " + reasons : ""}`);
        return false;
      }
      // Sub-fase 1.7 — 409 mixed-lot terstruktur (detail object). UI dialog menangani konfirmasi;
      // pesan fallback bila sampai ke sini tanpa konfirmasi.
      const msg = typeof detail === "object" && detail
        ? (detail.message || "Pesanan butuh konfirmasi lintas-lot.")
        : (detail || "Gagal membuat order/reservasi.");
      setNotice(msg);
      return false;
    }
  };

  const mutateOrder = async (path, successMessage) => {
    try {
      const response = await axios.post(`${API}${path}`);
      setNotice(successMessage(response.data));
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Aksi order gagal.");
    }
  };

  const payInvoice = async (orderId, amount) => {
    try {
      // Fase 1B — amount opsional; backend pakai grand_total order (sudah termasuk PPN)
      const body = { method: "Transfer Simulasi", created_by: user?.name || "Admin Demo" };
      if (amount && Number(amount) > 0) body.amount = Number(amount);
      const response = await axios.post(`${API}/sales-orders/${orderId}/simulate-payment`, body);
      setNotice(`Invoice ${response.data.number} dibuat (Rp ${formatQty(response.data.grand_total)} incl. PPN). SIMULATED payment.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Simulasi pembayaran gagal.");
    }
  };

  const approvePurchaseOrder = async (poId) => {
    try {
      const response = await axios.post(`${API}/purchase-orders/${poId}/approve`);
      setNotice(`PO ${response.data.po_number} disetujui. Inbound task otomatis dibuat.`);
      await loadAll();
      return response.data;
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal approve PO.");
      return null;
    }
  };

  const releaseReservation = async (orderId) => {
    try {
      const response = await axios.post(`${API}/sales-orders/${orderId}/release-reservation`);
      setNotice(`Reserved qty untuk order ${response.data.number} berhasil di-release. Status order → Draft.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal release reservation.");
    }
  };

  const markDelivered = async (orderId) => {
    try {
      const response = await axios.post(`${API}/sales-orders/${orderId}/mark-delivered`);
      setNotice(`Order ${response.data.number} ditandai DITERIMA (Selesai).`);
      await loadAll();
      return response.data;
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal menandai diterima.");
      return null;
    }
  };

  const issueTaxInvoice = async (orderId, payload = {}) => {
    try {
      const response = await axios.post(`${API}/sales-orders/${orderId}/tax-invoice`, payload);
      setNotice(`Faktur Pajak ${response.data.number} diterbitkan.`);
      await loadAll();
      return response.data;
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal menerbitkan Faktur Pajak.");
      return null;
    }
  };

  const generateDocument = async (documentType, orderId) => {
    try {
      const response = await axios.post(`${API}/documents/generate`, { document_type: documentType, source_id: orderId, actor: user?.name || "Admin Demo" });
      setLastDocument(response.data);
      setNotice(`Dokumen ${documentType} berhasil dibuat. Buka Print Center untuk mencetak.`);
      window.open(`${API}/documents/preview/${orderId}?document_type=${documentType}`, "_blank", "noopener,noreferrer");
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal generate dokumen.");
    }
  };

  const generateLabel = async (targetType, targetId) => {
    try {
      const validTargetType = ["product", "wms_task"].includes(targetType) ? targetType : "product";
      const response = await axios.post(`${API}/documents/barcode`, { target_type: validTargetType, target_id: targetId, label_size: "80x50mm" });
      setLastLabel({ label_html: response.data.label_html, code: targetId, label_size: "80x50mm", qr_matrix: [] });
      setActiveView("documents");
      setNotice(`Label barcode untuk ${targetType}/${targetId} berhasil dibuat.`);
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal generate label.");
    }
  };

  // Fase A — mengembalikan {ok, data, error} agar form (mis. master produk) bisa
  // menampilkan pesan validasi domain 400 secara inline, bukan hanya notice global.
  const adminCreate = async (resource, payload) => {
    try {
      const response = await axios.post(`${API}/${resource}`, payload);
      setNotice(`${resource} dibuat: ${response.data.name || response.data.code || response.data.email}`);
      await loadAll();
      return { ok: true, data: response.data };
    } catch (error) {
      const msg = error.response?.data?.detail || `Gagal membuat ${resource}.`;
      setNotice(msg);
      return { ok: false, error: typeof msg === "string" ? msg : JSON.stringify(msg) };
    }
  };

  const adminPatch = async (resource, id, dataPatch) => {
    try {
      const response = await axios.patch(`${API}/${resource}/${id}`, { data: dataPatch });
      setNotice(`${resource} berhasil diupdate.`);
      await loadAll();
      return { ok: true, data: response.data };
    } catch (error) {
      const msg = error.response?.data?.detail || `Gagal update ${resource}.`;
      setNotice(msg);
      return { ok: false, error: typeof msg === "string" ? msg : JSON.stringify(msg) };
    }
  };

  const adminDelete = async (resource, id) => {
    try {
      await axios.delete(`${API}/${resource}/${id}`);
      setNotice(`${resource} dinonaktifkan.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || `Gagal deactivate ${resource}.`);
    }
  };

  const importMaster = async (resource, file, dry_run = false) => {
    if (!file) { setNotice("Pilih file CSV/XLSX terlebih dahulu."); return; }
    const form = new FormData();
    form.append("file", file);
    try {
      const resourceMap = { products: "import-products", customers: "import-customers", warehouses: "import-warehouses" };
      const endpoint = resourceMap[resource] || `import-${resource}`;
      const url = `${API}/master-data/${endpoint}${dry_run ? "?dry_run=true" : ""}`;
      const response = await axios.post(url, form, { headers: { "Content-Type": "multipart/form-data" } });
      const created = response.data.created || 0;
      const updated = response.data.updated || 0;
      const errCount = (response.data.errors || []).length;
      if (dry_run) {
        setNotice(`Dry-run ${resource}: ${created} akan dibuat, ${updated} akan diupdate, ${errCount} error.`);
        return response.data;
      }
      setNotice(`Import ${resource}: ${created} dibuat, ${updated} diupdate, ${errCount} error.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || `Import ${resource} gagal.`);
    }
    return null;
  };

  const exportMaster = async (resource, _format) => {
    try {
      const resourceMap = { products: "export-products", customers: "export-customers", warehouses: "export-warehouses" };
      const endpoint = resourceMap[resource] || `export-${resource}`;
      const response = await axios.get(`${API}/master-data/${endpoint}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `kain_nusantara_${resource}.csv`;
      link.click();
      URL.revokeObjectURL(url);
      setNotice(`${resource} berhasil di-export sebagai CSV.`);
    } catch (error) {
      setNotice(error.response?.data?.detail || `Export ${resource} gagal.`);
    }
  };

  const updatePermissions = async (matrix, persist = true) => {
    setPermissions((current) => ({ ...current, matrix }));
    if (!persist) return;
    try {
      const response = await axios.put(`${API}/permissions`, { matrix });
      setPermissions((current) => ({ ...current, matrix: response.data.matrix }));
      setNotice("Permission matrix berhasil disimpan.");
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal menyimpan permission.");
    }
  };

  const seedDemo = async () => {
    const ok = await askConfirm({
      title: "Ganti SELURUH data operasional dengan data demo?",
      message: "Semua pesanan, stok, tugas gudang, pengguna, dan produk yang ada sekarang akan "
        + "DIHAPUS, lalu diganti data demo yang realistis. Tindakan ini tidak bisa dibatalkan.",
      confirmLabel: "Hapus & Isi Data Demo",
      danger: true,
      testId: "seed-demo-confirm",
    });
    if (!ok) return;
    setNotice("Sedang menjalankan seed demo... mohon tunggu 5–10 detik.");
    try {
      const response = await axios.post(`${API}/admin/seed-demo`, {
        confirm: "YES_CLEAR_AND_SEED_DEMO_DATA",
      });
      const s = response.data.summary || {};
      setNotice(
        `Seed sukses · ${s.products || 0} produk · ${s.sales_orders || 0} order · ` +
        `${s.inbound_tasks || 0} inbound · ${s.outbound_tasks || 0} outbound. ` +
        `Silakan refresh halaman.`
      );
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Seed gagal dijalankan.");
    }
  };

  const previewTemplate = async (templateId, orderId) => {
    try {
      const response = await axios.post(`${API}/document-templates/${templateId}/preview`, { document_type: "invoice", source_id: orderId, actor: user?.name || "Admin" }, { responseType: "text" });
      setPreviewHtml(response.data);
      setNotice("Preview template diperbarui.");
    } catch (error) {
      setNotice(error.response?.data?.detail || "Preview template gagal. Pastikan ada order untuk preview.");
    }
  };

  const refreshAudit = async () => {
    try {
      const params = new URLSearchParams(Object.entries(auditFilters).filter(([, value]) => value));
      const response = await axios.get(`${API}/audit-logs?${params.toString()}`);
      setAuditLogs(response.data);
      setNotice(`${response.data.length} audit/history record ditampilkan.`);
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal mengambil audit/history.");
    }
  };

  const createInboundTask = async (payload) => {
    try {
      const response = await axios.post(`${API}/wms/tasks`, { ...payload, flow_type: "inbound", source_type: "supplier" });
      setNotice(`Inbound task ${response.data.id} dibuat.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal membuat inbound task.");
    }
  };

  const createOutboundTasks = async (orderId) => {
    try {
      const response = await axios.post(`${API}/wms/tasks/outbound-from-order/${orderId}`);
      setNotice(`${response.data.length || 1} outbound task dibuat dari order.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal membuat outbound task.");
    }
  };

  const scanTask = async (taskId, scanType, scanValue) => {
    try {
      const response = await axios.post(`${API}/wms/tasks/${taskId}/scan`, { scan_type: scanType, scan_value: scanValue, actor: user?.name || "Warehouse" });
      setNotice(`Scan ${scanType} valid. Status task: ${response.data.status}.`);
      await loadAll();
      return true;
    } catch (error) {
      setNotice(error.response?.data?.detail || "Scan tidak valid.");
      return false;
    }
  };

  const advanceTask = async (taskId) => {
    try {
      const response = await axios.post(`${API}/wms/tasks/${taskId}/advance`);
      setNotice(`Task maju ke stage ${response.data.stage}.`);
      await loadAll();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Task belum bisa dilanjutkan.");
    }
  };

  // ── Notification Center (Fase 0) ──────────────────────────────────────────
  const loadNotifications = useCallback(async () => {
    const eq = (selectedEntity && selectedEntity !== "all") ? `?entity_id=${selectedEntity}` : "";
    try {
      const [n, u] = await Promise.all([
        axios.get(`${API}/notifications${eq}`),
        axios.get(`${API}/notifications/unread-count${eq}`),
      ]);
      setNotifications(Array.isArray(n.data) ? n.data : []);
      setUnreadCount(u.data?.count || 0);
    } catch (_) { /* silent */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEntity]);

  const markNotificationRead = async (id) => {
    try { await axios.post(`${API}/notifications/${id}/read`); await loadNotifications(); } catch (_) {}
  };

  const markAllNotificationsRead = async () => {
    const eq = (selectedEntity && selectedEntity !== "all") ? `?entity_id=${selectedEntity}` : "";
    try {
      await axios.post(`${API}/notifications/read-all${eq}`);
      await loadNotifications();
      setNotice("Semua notifikasi ditandai dibaca.");
    } catch (_) {}
  };

  const generateNotifications = async () => {
    try {
      const r = await axios.post(`${API}/notifications/generate`);
      setNotice(`Scan event selesai: ${r.data.created} notifikasi baru.`);
      await loadNotifications();
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal memindai notifikasi.");
    }
  };

  // Depth #3 — approve PO langsung dari kartu notifikasi.
  const approveFromNotification = async (notif) => {
    if (!notif?.action_id) return null;
    try {
      const res = await axios.post(`${API}/purchase-orders/${notif.action_id}/approve`);
      setNotice(`PO ${res.data.po_number} disetujui dari notifikasi. Inbound task dibuat.`);
      try { await axios.post(`${API}/notifications/${notif.id}/read`); } catch (_) {}
      await loadNotifications();
      await loadAll();
      return res.data;
    } catch (error) {
      setNotice(error.response?.data?.detail || "Gagal approve PO dari notifikasi.");
      return null;
    }
  };

  return {
    login, logout, showMetricDetail, loadAll,
    inspectProduct, addToCart, createCustomer, submitOrder, mutateOrder,
    payInvoice, releaseReservation, markDelivered, generateDocument, generateLabel,
    issueTaxInvoice,
    approvePurchaseOrder,
    adminCreate, adminPatch, adminDelete, importMaster, exportMaster,
    updatePermissions, seedDemo, previewTemplate, refreshAudit,
    createInboundTask, createOutboundTasks, scanTask, advanceTask,
    loadNotifications, markNotificationRead, markAllNotificationsRead, generateNotifications,
    approveFromNotification,
  };
}
