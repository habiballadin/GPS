"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";

type Customer = { id: number; name: string };
type Vehicle = { id: number; name: string };
type Driver = { id: number; name: string };
type Order = {
  id: number;
  reference: string;
  customer_id?: number;
  vehicle_id?: number;
  driver_id?: number;
  cargo_description?: string;
  cargo_weight_kg?: number;
  priority: string;
  status: string;
};
type Stop = {
  id: number;
  sequence: number;
  address: string;
  status: string;
  proof_note?: string;
  window_start?: string;
  window_end?: string;
  latitude?: number;
  longitude?: number;
};
type RouteSummary = {
  order_id: number;
  stops: number;
  mapped_stops: number;
  distance_m: number;
  estimated_minutes?: number;
  average_speed_kph: number;
  provider?: string;
  traffic_aware?: boolean;
  traffic_factor?: number;
};
type DeliveryException = {
  id: number;
  order_id: number;
  stop_id?: number;
  kind: string;
  message: string;
  status: string;
  created_at: string;
};
const headers = (token: string | null) => ({
  "Content-Type": "application/json",
  Authorization: `Bearer ${token}`,
});

export function DispatchWorkspace() {
  const { token } = useAuth();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [exceptions, setExceptions] = useState<DeliveryException[]>([]);
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [stops, setStops] = useState<Stop[]>([]);
  const [route, setRoute] = useState<RouteSummary | null>(null);
  const [deviation, setDeviation] = useState<{
    deviated: boolean;
    message: string;
    distance_to_next_stop_m?: number;
  } | null>(null);
  const [orderQuery, setOrderQuery] = useState("");
  const [orderStatus, setOrderStatus] = useState("all");
  const [orderPriority, setOrderPriority] = useState("all");
  const [customer, setCustomer] = useState({ name: "" });
  const [order, setOrder] = useState({
    reference: "",
    customer_id: "",
    cargo_description: "",
    cargo_weight_kg: "",
    priority: "normal",
  });
  const [assignment, setAssignment] = useState({
    vehicle_id: "",
    driver_id: "",
  });
  const [stop, setStop] = useState({
    address: "",
    latitude: "",
    longitude: "",
    window_start: "",
    window_end: "",
  });
  const load = async () => {
    if (!token) return;
    const auth = { Authorization: `Bearer ${token}` };
    const [c, v, d, o, x] = await Promise.all([
      fetch("/api/v1/customers", { headers: auth }),
      fetch("/api/v1/vehicles", { headers: auth }),
      fetch("/api/v1/drivers", { headers: auth }),
      fetch("/api/v1/delivery-orders", { headers: auth }),
      fetch("/api/v1/delivery-exceptions", { headers: auth }),
    ]);
    if (c.ok) setCustomers(await c.json());
    if (v.ok) setVehicles(await v.json());
    if (d.ok) setDrivers(await d.json());
    if (o.ok) setOrders(await o.json());
    if (x.ok) setExceptions(await x.json());
  };
  const loadStops = async (id: number) => {
    if (!token) return;
    setSelected(id);
    const response = await fetch(`/api/v1/delivery-orders/${id}/stops`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) setStops(await response.json());
    await loadRoute(id);
  };
  const loadRoute = async (id: number) => {
    if (!token) return;
    const response = await fetch(
      `/api/v1/delivery-orders/${id}/route-summary`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (response.ok) setRoute(await response.json());
  };
  const checkDeviation = async (id: number) => {
    if (!token) return;
    const response = await fetch(
      `/api/v1/delivery-orders/${id}/check-deviation`,
      { method: "POST", headers: { Authorization: `Bearer ${token}` } },
    );
    const data = await response.json().catch(() => null);
    setDeviation(response.ok ? data : null);
    setMessage(
      response.ok ? data.message : (data?.detail ?? "Could not check route"),
    );
  };
  const optimizeRoute = async (id: number) => {
    if (!token) return;
    const response = await fetch(`/api/v1/delivery-orders/${id}/optimize-route`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await response.json().catch(() => null);
    setMessage(response.ok ? "Route optimized and stop sequence updated." : (data?.detail ?? "Could not optimize route"));
    if (response.ok) {
      await loadStops(id);
    }
  };
  useEffect(() => {
    void load();
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps
  const submitCustomer = async (e: FormEvent) => {
    e.preventDefault();
    const r = await fetch("/api/v1/customers", {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify(customer),
    });
    setMessage(r.ok ? "Customer added." : "Could not add customer");
    if (r.ok) {
      setCustomer({ name: "" });
      await load();
    }
  };
  const submitOrder = async (e: FormEvent) => {
    e.preventDefault();
    const r = await fetch("/api/v1/delivery-orders", {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({
        ...order,
        customer_id: order.customer_id ? Number(order.customer_id) : null,
        cargo_weight_kg: order.cargo_weight_kg
          ? Number(order.cargo_weight_kg)
          : null,
      }),
    });
    if (!r.ok) {
      setMessage(
        (await r.json().catch(() => null))?.detail ?? "Could not create order",
      );
      return;
    }
    setMessage("Delivery order created.");
    setOrder({
      reference: "",
      customer_id: "",
      cargo_description: "",
      cargo_weight_kg: "",
      priority: "normal",
    });
    await load();
  };
  const assign = async (id: number) => {
    const r = await fetch(`/api/v1/delivery-orders/${id}/assign`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({
        vehicle_id: Number(assignment.vehicle_id),
        driver_id: Number(assignment.driver_id),
      }),
    });
    setMessage(
      r.ok
        ? "Order assigned."
        : ((await r.json().catch(() => null))?.detail ??
            "Could not assign order"),
    );
    if (r.ok) await load();
  };
  const addStop = async (e: FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    const r = await fetch(`/api/v1/delivery-orders/${selected}/stops`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({
        address: stop.address,
        latitude: stop.latitude ? Number(stop.latitude) : null,
        longitude: stop.longitude ? Number(stop.longitude) : null,
        window_start: stop.window_start
          ? new Date(stop.window_start).toISOString()
          : null,
        window_end: stop.window_end
          ? new Date(stop.window_end).toISOString()
          : null,
      }),
    });
    setMessage(r.ok ? "Stop added." : "Could not add stop");
    if (r.ok) {
      setStop({
        address: "",
        window_start: "",
        window_end: "",
        latitude: "",
        longitude: "",
      });
      await loadStops(selected);
      await loadRoute(selected);
    }
  };
  const completeStop = async (id: number) => {
    const proof_note = window.prompt("Proof-of-delivery note (optional)") ?? "";
    const r = await fetch(`/api/v1/delivery-stops/${id}/complete`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({ proof_note }),
    });
    setMessage(r.ok ? "Stop completed." : "Could not complete stop");
    if (r.ok && selected) {
      await loadStops(selected);
      await load();
    }
  };
  const resolveException = async (id: number) => {
    const r = await fetch(`/api/v1/delivery-exceptions/${id}/resolve`, {
      method: "POST",
      headers: headers(token),
    });
    setMessage(r.ok ? "Exception resolved." : "Could not resolve exception");
    if (r.ok) await load();
  };
  const name = (items: Array<{ id: number; name: string }>, id?: number) =>
    items.find((x) => x.id === id)?.name ?? "Unassigned";
  const filteredOrders = useMemo(
    () => orders.filter((item) => `${item.reference} ${item.cargo_description ?? ""}`.toLowerCase().includes(orderQuery.toLowerCase()) && (orderStatus === "all" || item.status === orderStatus) && (orderPriority === "all" || item.priority === orderPriority)),
    [orders, orderQuery, orderStatus, orderPriority],
  );
  return (
    <section>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">
            Dispatch operations
          </p>
          <h1 className="text-3xl font-bold tracking-tight">
            Orders and delivery execution
          </h1>
          <p className="mt-2 text-slate-500">
            Create customer jobs, assign a vehicle and driver, then execute each
            stop in sequence.
          </p>
        </div>
      </div>
      {message && (
        <p className="mb-5 rounded-xl bg-mist p-3 text-sm text-forest">
          {message}
        </p>
      )}
      <div className="grid gap-6 xl:grid-cols-2">
        <form
          onSubmit={submitCustomer}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"
        >
          <h2 className="text-lg font-bold">1. Add customer</h2>
          <input
            required
            className="mt-5 w-full rounded-xl border border-slate-200 p-3"
            placeholder="Customer name"
            value={customer.name}
            onChange={(e) => setCustomer({ name: e.target.value })}
          />
          <button className="mt-4 w-full rounded-xl bg-forest p-3 font-bold text-white">
            Add customer
          </button>
        </form>
        <form
          onSubmit={submitOrder}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"
        >
          <h2 className="text-lg font-bold">2. Create delivery order</h2>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <input
              required
              className="rounded-xl border border-slate-200 p-3"
              placeholder="Order reference"
              value={order.reference}
              onChange={(e) =>
                setOrder({ ...order, reference: e.target.value })
              }
            />
            <select
              className="rounded-xl border border-slate-200 p-3"
              value={order.customer_id}
              onChange={(e) =>
                setOrder({ ...order, customer_id: e.target.value })
              }
            >
              <option value="">Customer (optional)</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <input
              className="rounded-xl border border-slate-200 p-3"
              placeholder="Cargo description"
              value={order.cargo_description}
              onChange={(e) =>
                setOrder({ ...order, cargo_description: e.target.value })
              }
            />
            <input
              min="0"
              type="number"
              className="rounded-xl border border-slate-200 p-3"
              placeholder="Cargo weight (kg)"
              value={order.cargo_weight_kg}
              onChange={(e) =>
                setOrder({ ...order, cargo_weight_kg: e.target.value })
              }
            />
          </div>
          <button className="mt-4 w-full rounded-xl bg-forest p-3 font-bold text-white">
            Create order
          </button>
        </form>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <div className="flex items-center justify-between gap-3"><h2 className="text-lg font-bold">Dispatch board</h2><span className="rounded-full bg-mist px-3 py-1 text-xs font-bold text-forest">{filteredOrders.length}/{orders.length}</span></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_150px_150px]"><input aria-label="Search orders" className="rounded-xl border border-slate-200 p-3 text-sm" placeholder="Search reference or cargo" value={orderQuery} onChange={(e) => setOrderQuery(e.target.value)} /><select aria-label="Filter order status" className="rounded-xl border border-slate-200 p-3 text-sm" value={orderStatus} onChange={(e) => setOrderStatus(e.target.value)}><option value="all">All statuses</option><option value="unassigned">Unassigned</option><option value="assigned">Assigned</option><option value="in_progress">In progress</option><option value="completed">Completed</option></select><select aria-label="Filter order priority" className="rounded-xl border border-slate-200 p-3 text-sm" value={orderPriority} onChange={(e) => setOrderPriority(e.target.value)}><option value="all">All priorities</option><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option></select></div>
          <div className="mt-4 space-y-3">
            {filteredOrders.map((o) => (
              <article key={o.id} className="rounded-xl bg-mist p-4">
                <div className="flex flex-wrap justify-between gap-3">
                  <div>
                    <strong>{o.reference}</strong>
                    <p className="mt-1 text-sm text-slate-500">
                      {name(customers, o.customer_id)} ·{" "}
                      {o.cargo_description || "No cargo details"} ·{" "}
                      {o.cargo_weight_kg ?? "—"} kg
                    </p>
                    <p className="mt-1 text-xs text-slate-400">
                      {name(vehicles, o.vehicle_id)} /{" "}
                      {name(drivers, o.driver_id)} · {o.status}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold"
                      onClick={() => void loadStops(o.id)}
                    >
                      Stops
                    </button>
                    <button
                      className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold"
                      onClick={() => void checkDeviation(o.id)}
                    >
                      Check route
                    </button>
                  </div>
                </div>
                {o.status === "unassigned" && (
                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    <select
                      className="rounded-lg border border-slate-200 p-2 text-sm"
                      value={assignment.vehicle_id}
                      onChange={(e) =>
                        setAssignment({
                          ...assignment,
                          vehicle_id: e.target.value,
                        })
                      }
                    >
                      <option value="">Vehicle</option>
                      {vehicles.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name}
                        </option>
                      ))}
                    </select>
                    <select
                      className="rounded-lg border border-slate-200 p-2 text-sm"
                      value={assignment.driver_id}
                      onChange={(e) =>
                        setAssignment({
                          ...assignment,
                          driver_id: e.target.value,
                        })
                      }
                    >
                      <option value="">Driver</option>
                      {drivers.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                    <button
                      disabled={!assignment.vehicle_id || !assignment.driver_id}
                      onClick={() => void assign(o.id)}
                      className="rounded-lg bg-forest px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
                    >
                      Assign
                    </button>
                  </div>
                )}
              </article>
            ))}
            {!filteredOrders.length && (
              <p className="py-10 text-center text-sm text-slate-400">
                {orders.length ? "No orders match these filters." : "No delivery orders yet."}
              </p>
            )}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <h2 className="text-lg font-bold">
            {selected ? "Stops" : "Select an order"}
          </h2>
          {selected && (
            <>
              <form className="mt-4 grid gap-3" onSubmit={addStop}>
                <input
                  required
                  className="w-full rounded-xl border border-slate-200 p-3"
                  placeholder="Stop address"
                  value={stop.address}
                  onChange={(e) =>
                    setStop({ ...stop, address: e.target.value })
                  }
                />
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="number"
                    step="any"
                    aria-label="Latitude"
                    placeholder="Latitude"
                    className="rounded-xl border border-slate-200 p-3 text-sm"
                    value={stop.latitude}
                    onChange={(e) =>
                      setStop({ ...stop, latitude: e.target.value })
                    }
                  />
                  <input
                    type="number"
                    step="any"
                    aria-label="Longitude"
                    placeholder="Longitude"
                    className="rounded-xl border border-slate-200 p-3 text-sm"
                    value={stop.longitude}
                    onChange={(e) =>
                      setStop({ ...stop, longitude: e.target.value })
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="datetime-local"
                    aria-label="Window start"
                    className="rounded-xl border border-slate-200 p-3 text-sm"
                    value={stop.window_start}
                    onChange={(e) =>
                      setStop({ ...stop, window_start: e.target.value })
                    }
                  />
                  <input
                    type="datetime-local"
                    aria-label="Window end"
                    className="rounded-xl border border-slate-200 p-3 text-sm"
                    value={stop.window_end}
                    onChange={(e) =>
                      setStop({ ...stop, window_end: e.target.value })
                    }
                  />
                </div>
                <button className="w-full rounded-xl bg-forest p-3 font-bold text-white">
                  Add stop
                </button>
              </form>
              {route && (
                <div className="mt-4 grid grid-cols-2 gap-2 rounded-xl bg-lime/20 p-3 text-sm">
                  <span>
                    <strong className="block text-lg">
                      {(route.distance_m / 1000).toFixed(1)} km
                    </strong>
                    Route distance
                  </span>
                  <span>
                    <strong className="block text-lg">
                      {route.estimated_minutes?.toFixed(0) ?? "—"} min
                    </strong>
                    Estimated travel
                  </span>
                  <span>
                    {route.mapped_stops}/{route.stops} stops mapped
                  </span>
                  <div className="flex justify-end gap-3 text-xs font-bold text-forest">
                    <button onClick={() => selected && void optimizeRoute(selected)}>
                      Optimize sequence
                    </button>
                    <button onClick={() => selected && void loadRoute(selected)}>
                      Refresh route
                    </button>
                  </div>
                  <span className="col-span-2 text-xs text-slate-500">
                    {route.provider ?? "straight_line"}{route.traffic_aware ? " · traffic-aware" : " · fallback estimate"}
                  </span>
                </div>
              )}
              {deviation && (
                <div
                  className={`mt-3 rounded-xl p-3 text-sm ${deviation.deviated ? "bg-red-50 text-red-700" : "bg-lime/20 text-forest"}`}
                >
                  {deviation.message}
                  {deviation.distance_to_next_stop_m
                    ? ` (${(deviation.distance_to_next_stop_m / 1000).toFixed(1)} km away)`
                    : ""}
                </div>
              )}
              <div className="mt-5 space-y-3">
                {stops.map((s) => (
                  <article
                    key={s.id}
                    className="flex items-center justify-between gap-3 rounded-xl bg-mist p-3"
                  >
                    <span>
                      <strong>#{s.sequence}</strong> · {s.address}
                      {s.window_end && (
                        <small className="block text-slate-500">
                          Window ends {new Date(s.window_end).toLocaleString()}
                        </small>
                      )}
                    </span>
                    {s.status === "completed" ? (
                      <span className="text-xs font-bold text-forest">
                        Completed
                      </span>
                    ) : (
                      <button
                        className="text-xs font-bold text-forest"
                        onClick={() => void completeStop(s.id)}
                      >
                        Complete
                      </button>
                    )}
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">Open delivery exceptions</h2>
          <span className="text-sm text-slate-400">
            {exceptions.length} open
          </span>
        </div>
        <div className="mt-4 space-y-3">
          {exceptions.map((item) => (
            <article
              key={item.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 p-4"
            >
              <div>
                <strong className="uppercase text-amber-800">
                  {item.kind.replace("_", " ")}
                </strong>
                <p className="mt-1 text-sm text-slate-600">{item.message}</p>
                <p className="mt-1 text-xs text-slate-400">
                  Order #{item.order_id} ·{" "}
                  {new Date(item.created_at).toLocaleString()}
                </p>
              </div>
              <button
                onClick={() => void resolveException(item.id)}
                className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-bold text-amber-900"
              >
                Resolve
              </button>
            </article>
          ))}
          {!exceptions.length && (
            <p className="py-8 text-center text-sm text-slate-400">
              No open delivery exceptions.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
