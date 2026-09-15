"use client";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
type Device = {
  id: number;
  imei: string;
  protocol: string;
  model?: string;
  firmware_version?: string;
  status: string;
  vehicle_id?: number;
};
type Health = {
  device_id: number;
  health: "online" | "stale" | "offline" | "never_seen";
  freshness_seconds?: number;
};
type Vehicle = { id: number; name: string };
type Command = {
  id: number;
  command: string;
  status: string;
  response?: string;
  created_at: string;
};
type Protocol = { key: string; label: string };
export function DeviceRegistry() {
  const { token } = useAuth();
  const [devices, setDevices] = useState<Device[]>([]);
  const [health, setHealth] = useState<Health[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [commands, setCommands] = useState<Command[]>([]);
  const [protocols, setProtocols] = useState<Protocol[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [command, setCommand] = useState("");
  const [form, setForm] = useState({
    imei: "",
    protocol: "teltonika",
    model: "",
    firmware_version: "",
  });
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [healthFilter, setHealthFilter] = useState("all");
  const auth = () => ({ Authorization: `Bearer ${token}` });
  const load = async () => {
    if (!token) return;
    const h = auth();
    const [d, v, he, p] = await Promise.all([
      fetch("/api/v1/devices", { headers: h }),
      fetch("/api/v1/vehicles", { headers: h }),
      fetch("/api/v1/devices/health", { headers: h }),
      fetch("/api/v1/devices/protocols", { headers: h }),
    ]);
    if (d.ok) setDevices(await d.json());
    if (v.ok) setVehicles(await v.json());
    if (he.ok) setHealth(await he.json());
    if (p.ok) {
      const available = (await p.json()) as Protocol[];
      setProtocols(available);
      if (
        available.length &&
        !available.some((item) => item.key === form.protocol)
      )
        setForm((current) => ({ ...current, protocol: available[0].key }));
    }
  };
  const select = async (id: number) => {
    setSelected(id);
    if (!token) return;
    const r = await fetch(`/api/v1/devices/${id}/commands`, {
      headers: auth(),
    });
    if (r.ok) setCommands(await r.json());
  };
  useEffect(() => {
    void load();
  }, [token]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const r = await fetch("/api/v1/devices", {
      method: "POST",
      headers: { ...auth(), "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setMessage(
      r.ok
        ? "Device registered."
        : ((await r.json().catch(() => null))?.detail ??
            "Could not register device"),
    );
    if (r.ok) {
      setForm({
        imei: "",
        protocol: "teltonika",
        model: "",
        firmware_version: "",
      });
      await load();
    }
  };
  const bind = async (device: Device) => {
    const id = window.prompt(`Vehicle ID to bind ${device.imei}`);
    if (!id) return;
    const r = await fetch(`/api/v1/devices/${device.id}/bind/${id}`, {
      method: "POST",
      headers: auth(),
    });
    setMessage(
      r.ok
        ? "Device bound."
        : ((await r.json().catch(() => null))?.detail ??
            "Could not bind device"),
    );
    if (r.ok) await load();
  };
  const issue = async (e: FormEvent) => {
    e.preventDefault();
    if (!selected || !command.trim()) return;
    const r = await fetch(`/api/v1/devices/${selected}/commands`, {
      method: "POST",
      headers: { ...auth(), "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    setMessage(
      r.ok
        ? "Command sent."
        : ((await r.json().catch(() => null))?.detail ?? "Command failed"),
    );
    if (r.ok) {
      setCommand("");
      await select(selected);
    }
  };
  const vehicleName = (id?: number) =>
    vehicles.find((v) => v.id === id)?.name ?? "Unbound";
  const state = (id: number) => health.find((h) => h.device_id === id);
  const filteredDevices = useMemo(
    () =>
      devices.filter((device) => {
        const item = state(device.id);
        return (
          `${device.imei} ${device.model ?? ""} ${vehicleName(device.vehicle_id)}`
            .toLowerCase()
            .includes(query.toLowerCase()) &&
          (healthFilter === "all" || item?.health === healthFilter)
        );
      }),
    [devices, health, query, healthFilter],
  );
  return (
    <section>
      <div className="mb-8">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-forest">
          Telematics
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Devices</h1>
        <p className="mt-2 text-slate-500">
          Monitor tracker freshness, binding, and command acknowledgements.
        </p>
      </div>
      {message && (
        <p className="mb-5 rounded-xl bg-mist p-3 text-sm text-forest">
          {message}
        </p>
      )}
      <div className="grid gap-6 xl:grid-cols-[0.7fr_1.3fr]">
        <form
          onSubmit={submit}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"
        >
          <h2 className="text-lg font-bold">Register device</h2>
          <div className="mt-5 space-y-4">
            <input
              required
              className="w-full rounded-xl border border-slate-200 p-3"
              placeholder="IMEI"
              value={form.imei}
              onChange={(e) => setForm({ ...form, imei: e.target.value })}
            />
            <select
              className="w-full rounded-xl border border-slate-200 p-3"
              value={form.protocol}
              onChange={(e) => setForm({ ...form, protocol: e.target.value })}
            >
              {protocols.length ? protocols.map((protocol) => <option key={protocol.key} value={protocol.key}>{protocol.label}</option>) : <option value="teltonika">Teltonika Codec 8/8E</option>}
            </select>
            <input
              className="w-full rounded-xl border border-slate-200 p-3"
              placeholder="Device model"
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
            />
            <input
              className="w-full rounded-xl border border-slate-200 p-3"
              placeholder="Firmware version"
              value={form.firmware_version}
              onChange={(e) =>
                setForm({ ...form, firmware_version: e.target.value })
              }
            />
            <button className="w-full rounded-xl bg-forest p-3 font-bold text-white">
              Register device
            </button>
          </div>
        </form>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold">Device registry</h2>
            <button
              onClick={() => void load()}
              className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold"
            >
              Refresh
            </button>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_150px]">
            <input
              aria-label="Search devices"
              className="rounded-xl border border-slate-200 p-3 text-sm"
              placeholder="Search IMEI, model, or vehicle"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <select
              aria-label="Filter device health"
              className="rounded-xl border border-slate-200 p-3 text-sm"
              value={healthFilter}
              onChange={(e) => setHealthFilter(e.target.value)}
            >
              <option value="all">All health</option>
              <option value="online">Online</option>
              <option value="stale">Stale</option>
              <option value="offline">Offline</option>
              <option value="never_seen">Never seen</option>
            </select>
          </div>
          <div className="mt-5 space-y-3">
            {filteredDevices.map((device) => {
              const item = state(device.id);
              return (
                <article key={device.id} className="rounded-xl bg-mist p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <strong>{device.imei}</strong>
                      <p className="mt-1 text-sm text-slate-500">
                        {device.protocol} · {device.model || "Unknown model"} ·{" "}
                        {vehicleName(device.vehicle_id)}
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-bold uppercase ${item?.health === "online" ? "bg-lime text-forest" : item?.health === "stale" ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"}`}
                    >
                      {item?.health ?? "unknown"}
                    </span>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => void bind(device)}
                      className="rounded-lg bg-forest px-3 py-2 text-xs font-bold text-white"
                    >
                      Bind vehicle
                    </button>
                    <button
                      onClick={() => void select(device.id)}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-bold"
                    >
                      Commands
                    </button>
                  </div>
                </article>
              );
            })}
            {!filteredDevices.length && (
              <p className="py-10 text-center text-sm text-slate-400">
                {devices.length
                  ? "No devices match these filters."
                  : "No devices registered yet."}
              </p>
            )}
          </div>
        </div>
      </div>
      {selected && (
        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <form
            onSubmit={issue}
            className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel"
          >
            <h2 className="text-lg font-bold">Send command</h2>
            <input
              required
              className="mt-5 w-full rounded-xl border border-slate-200 p-3 font-mono"
              placeholder="e.g. getparam 2000"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
            />
            <button className="mt-4 w-full rounded-xl bg-forest p-3 font-bold text-white">
              Send to device
            </button>
          </form>
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-panel">
            <h2 className="text-lg font-bold">Command history</h2>
            <div className="mt-4 space-y-2">
              {commands.map((item) => (
                <div className="rounded-xl bg-mist p-3 text-sm" key={item.id}>
                  <div className="flex justify-between">
                    <code>{item.command}</code>
                    <span className="font-bold uppercase text-forest">
                      {item.status}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    {new Date(item.created_at).toLocaleString()}
                    {item.response ? ` · ${item.response}` : ""}
                  </p>
                </div>
              ))}
              {!commands.length && (
                <p className="py-8 text-center text-sm text-slate-400">
                  No commands yet.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
