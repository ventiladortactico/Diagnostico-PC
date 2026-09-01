// OptiChek checkout con Mercado Pago.
// Rutas:
//   POST /checkout/user   -> crea el pago y devuelve init_point (requiere sesion del tecnico)
//   POST /checkout/qr     -> crea orden QR dinamica y devuelve qr_data (requiere sesion)
//   POST /checkout/webhook -> confirmacion de Mercado Pago (activa la suscripcion si el pago es aprobado)
//   GET  /checkout/estado  -> vence de la suscripcion actual (requiere sesion)
//
// Secretos (configurar en Supabase / Edge Functions):
//   MP_ACCESS_TOKEN  : token de Mercado Pago (pais AR)
//   MP_PRICE         : precio en pesos (ARS) de la suscripcion anual
//   MP_POS_ID        : external_pos_id del POS de QR (ej: OPTICHEKQR001)
//   (SUPABASE_URL, SUPABASE_ANON_KEY y SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase solo)

const MP_API = "https://api.mercadopago.com";

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}

async function mp(path, body) {
  const res = await fetch(MP_API + path, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${Deno.env.get("MP_ACCESS_TOKEN") ?? ""}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

async function tecnicoIdDeJwt(jwt) {
  try {
    const base = Deno.env.get("SUPABASE_URL") ?? "";
    const anon = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
    const r = await fetch(`${base}/auth/v1/user`, {
      headers: { apikey: anon, Authorization: `Bearer ${jwt}` },
    });
    if (!r.ok) return null;
    const u = await r.json();
    return u.id ?? null;
  } catch {
    return null;
  }
}

async function rpcRenovar(tecnicoId, dias) {
  const base = Deno.env.get("SUPABASE_URL") ?? "";
  const sk = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const res = await fetch(`${base}/rest/v1/rpc/renovar_por_pago`, {
    method: "POST",
    headers: {
      apikey: sk,
      Authorization: `Bearer ${sk}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ p_tecnico_id: tecnicoId, p_dias: dias }),
  });
  return res;
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const path = (url.pathname || "").split("/").filter(Boolean).pop() ?? "";
  const jwt = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");

  if (req.method === "POST" && path === "user") {
    const uid = await tecnicoIdDeJwt(jwt);
    if (!uid) return json({ error: "AUTH_REQUERIDA" }, 401);
    const precio = Number(Deno.env.get("MP_PRICE") ?? "0");
    if (precio <= 0) return json({ error: "PRICE_NO_CONFIGURADO" }, 500);
    const base = Deno.env.get("SUPABASE_URL") ?? "";
    const pref = await mp("/checkout/preferences", {
      items: [
        {
          title: "Suscripcion OptiChek - 1 anio",
          quantity: 1,
          currency_id: "ARS",
          unit_price: precio,
        },
      ],
      external_reference: uid,
      metadata: { tecnico_id: uid },
      notification_url: `${base}/functions/v1/checkout/webhook`,
      back_urls: { fail: `${base}/functions/v1/checkout`, pending: `${base}/functions/v1/checkout` },
    });
    if (!pref.init_point) {
      return json({ error: "MP_ERROR", detail: pref.message ?? pref.error ?? "" }, 502);
    }
    return json({ init_point: pref.init_point, precio });
  }

  if (req.method === "POST" && path === "qr") {
    const uid = await tecnicoIdDeJwt(jwt);
    if (!uid) return json({ error: "AUTH_REQUERIDA" }, 401);
    const precio = Number(Deno.env.get("MP_PRICE") ?? "0");
    if (precio <= 0) return json({ error: "PRICE_NO_CONFIGURADO" }, 500);
    const posId = Deno.env.get("MP_POS_ID") ?? "";
    if (!posId) return json({ error: "POS_NO_CONFIGURADO" }, 500);
    const extRef = "oc-" + crypto.randomUUID().replace(/-/g, "").slice(0, 16);
    const body = {
      type: "qr",
      total_amount: String(precio),
      description: "Suscripcion OptiChek - 1 anio",
      external_reference: extRef,
      expiration_time: "PT30M",
      config: { qr: { external_pos_id: posId, mode: "dynamic" } },
      transactions: { payments: [{ amount: String(precio) }] },
      items: [{ title: "Suscripcion OptiChek - 1 anio", unit_price: String(precio), unit_measure: "unit", quantity: 1 }],
    };
    const r = await fetch(MP_API + "/v1/orders", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${Deno.env.get("MP_ACCESS_TOKEN") ?? ""}`,
        "Content-Type": "application/json",
        "X-Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    const qrData = data?.type_response?.qr_data;
    if (!qrData) {
      return json({ error: "MP_ERROR", detail: JSON.stringify(data).slice(0, 500) }, 502);
    }
    return json({ qr_data: qrData, order_id: data.id, external_reference: extRef });
  }

  if (req.method === "POST" && path === "webhook") {
    let cuerpo = {};
    try {
      cuerpo = await req.json();
    } catch {}
    const topic = url.searchParams.get("topic") ?? cuerpo?.topic ?? "";
    if (topic === "payment" || (cuerpo?.data?.id && !topic)) {
      const pagoId = cuerpo?.data?.id ?? url.searchParams.get("data.id") ?? url.searchParams.get("data_id");
      if (!pagoId) return json({ ok: true });
      const pago = await mp(`/v1/payments/${pagoId}`);
      if (pago.status !== "approved") return json({ ok: true, nota: "no_aprobado" });
      const precio = Number(Deno.env.get("MP_PRICE") ?? "0");
      const uid = pago?.metadata?.tecnico_id || pago?.external_reference;
      if (!uid) return json({ ok: false, error: "SIN_REFERENCIA" }, 400);
      if (precio > 0 && Number(pago.transaction_amount) < precio) {
        return json({ ok: false, error: "MONTO_INCORRECTO" }, 400);
      }
      const res = await rpcRenovar(uid, 365);
      if (!res.ok) {
        return json({ ok: false, error: "DB_ERROR", detail: await res.text() }, 502);
      }
      return json({ ok: true });
    }
    if (topic === "order" || topic === "merchant_order") {
      const orderId = cuerpo?.id ?? cuerpo?.data?.id ?? "";
      if (!orderId) return json({ ok: true });
      const order = await mp(`/v1/orders/${orderId}`);
      if (order.status !== "paid") return json({ ok: true, nota: "order_not_paid" });
      const precio = Number(Deno.env.get("MP_PRICE") ?? "0");
      const extRef = order.external_reference || "";
      let uid = extRef.startsWith("oc-") ? "" : extRef;
      if (!uid) {
        const pays = order?.transactions?.payments ?? [];
        if (pays.length > 0 && pays[0].id) {
          const pago = await mp(`/v1/payments/${pays[0].id}`);
          uid = pago?.metadata?.tecnico_id || pago?.external_reference || "";
        }
      }
      if (!uid) {
        const morder = await mp(`/merchant_orders?external_reference=${extRef}`);
        const items = morder?.results ?? [];
        if (items.length > 0) uid = items[0].external_reference || "";
      }
      if (!uid || uid.startsWith("oc-")) return json({ ok: false, error: "SIN_REFERENCIA" }, 400);
      const res = await rpcRenovar(uid, 365);
      if (!res.ok) {
        return json({ ok: false, error: "DB_ERROR", detail: await res.text() }, 502);
      }
      return json({ ok: true });
    }
    return json({ ok: true });
  }

  if (req.method === "GET" && path === "estado") {
    const uid = await tecnicoIdDeJwt(jwt);
    if (!uid) return json({ error: "AUTH_REQUERIDA" }, 401);
    const base = Deno.env.get("SUPABASE_URL") ?? "";
    const anon = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
    const res = await fetch(
      `${base}/rest/v1/suscripciones?select=vence&tecnico_id=eq.${uid}&order=vence.desc&limit=1`,
      {
        headers: { apikey: anon, Authorization: `Bearer ${jwt}` },
      },
    );
    if (!res.ok) return json({ error: "DB_ERROR" }, 502);
    const filas = await res.json();
    const vence = Array.isArray(filas) && filas[0]?.vence ? filas[0].vence : "";
    const activa = !!vence && vence >= new Date().toISOString().slice(0, 10);
    return json({ vence, activa });
  }

  return json({ error: "RUTA_NO_ENCONTRADA" }, 404);
});