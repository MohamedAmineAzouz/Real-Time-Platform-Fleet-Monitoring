import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { TruckService, Truck } from './truck.service';
import { CommonModule } from '@angular/common';

interface TruckState {
  marker: any;
  currentLat: number;
  currentLng: number;
  targetLat: number;
  targetLng: number;
  lastUpdateTime: number;
}

@Component({
  standalone: true,
  imports: [CommonModule],
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent implements OnInit, OnDestroy {
  trucks: Truck[] = [];
  selectedTruck: Truck | null = null;
  isLoading = true;
  lastUpdated: Date = new Date();

  private intervalId: any;
  private map: any;
  private truckStates: Map<number, TruckState> = new Map();

  // ── Route state ──────────────────────────────────────────────────────────
  // The raw OSRM lat/lng array — fetched ONCE per route, never again
  private cachedRouteLatLngs: [number, number][] = [];
  // The two live polyline objects on the map (updated in-place, never removed/re-added)
  private completedPolyline: any = null;
  private remainingPolyline: any = null;
  // Which route the cache belongs to
  private cachedRoute: { startCity: string; endCity: string } | null = null;
  // Active fetch token — only used to cancel a fetch if user closes/switches
  // BEFORE the first fetch for a new route completes
  private routeDrawToken = 0;
  // The truck_id whose route is currently displayed
  private activeRouteTruckId: number | null = null;

  private readonly OSRM_URL = 'https://router.project-osrm.org/route/v1/driving/';
  private readonly ANIMATION_DURATION = 1800;
  private readonly EASING = (t: number) => t < .5 ? 2 * t * t : -1 + (4 - 2 * t) * t;

  constructor(private truckService: TruckService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.loadLeaflet().then(() => {
      this.initMap();
      this.loadTrucks();
      this.intervalId = setInterval(() => this.loadTrucks(), 2000);
      this.startAnimationLoop();
    });
  }

  ngOnDestroy(): void {
    if (this.intervalId) clearInterval(this.intervalId);
    if (this.map) this.map.remove();
  }

  // ─────────────────────────────────────────────
  // Leaflet bootstrap
  // ─────────────────────────────────────────────

  private loadLeaflet(): Promise<void> {
    return new Promise((resolve) => {
      if ((window as any).L) { resolve(); return; }
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = () => resolve();
      document.head.appendChild(script);
    });
  }

  private initMap(): void {
    const L = (window as any).L;
    this.map = L.map('map', { center: [31.7917, -7.0926], zoom: 6, zoomControl: false });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap © CARTO', maxZoom: 19
    }).addTo(this.map);
    L.control.zoom({ position: 'bottomright' }).addTo(this.map);
  }

  // ─────────────────────────────────────────────
  // Animation loop
  // ─────────────────────────────────────────────

  private startAnimationLoop(): void {
    const animate = () => {
      const now = performance.now();
      this.truckStates.forEach(state => this.applyInterpolation(state, now));
      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }

  private applyInterpolation(state: TruckState, now: number): void {
    const elapsed = now - state.lastUpdateTime;
    const t = Math.min(elapsed / this.ANIMATION_DURATION, 1);
    const e = this.EASING(t);
    const lat = state.currentLat + (state.targetLat - state.currentLat) * e;
    const lng = state.currentLng + (state.targetLng - state.currentLng) * e;
    state.marker.setLatLng([lat, lng]);
  }

  // ─────────────────────────────────────────────
  // Truck selection
  // ─────────────────────────────────────────────

  selectTruck(truck: Truck): void {
    this.selectedTruck = truck;
    if (this.map) {
      this.map.flyTo([truck.latitude, truck.longitude], 12, { duration: 1.2, easeLinearity: 0.25 });
      this.ensureRouteLines(truck);
    }
    this.cdr.detectChanges();
  }

  closeSidebar(): void {
    this.selectedTruck = null;
    this.activeRouteTruckId = null;
    this.routeDrawToken++;       // cancel any in-flight fetch
    this.destroyPolylines();
    this.cachedRouteLatLngs = [];
    this.cachedRoute = null;
  }

  // ─────────────────────────────────────────────
  // Route management — fetch once, update in-place
  // ─────────────────────────────────────────────

  /**
   * Called when a truck is selected OR when its position changes while selected.
   * - If the route (start→end cities) hasn't changed: just reposition the split point,
   *   NO fetch, NO flicker.
   * - If the route changed (different truck or different journey): fetch once, then cache.
   */
  private ensureRouteLines(truck: Truck): void {
    const L = (window as any).L;
    if (!this.map || !L) return;

    const startCity = (truck as any).start_city;
    const endCity   = (truck as any).end_city;
    if (!startCity || !endCity) return;

    const isSameRoute =
      this.cachedRoute?.startCity === startCity &&
      this.cachedRoute?.endCity   === endCity;

    if (isSameRoute && this.cachedRouteLatLngs.length > 0) {
      // ── Route geometry already cached — just move the split point ──
      this.updatePolylineSplit(truck);
      return;
    }

    // ── New route: fetch geometry once, then cache it ──
    const startCoords = this.getCityCoords(startCity);
    const endCoords   = this.getCityCoords(endCity);
    if (!startCoords || !endCoords) return;

    // Cancel any previous in-flight fetch for a different route
    this.destroyPolylines();
    this.cachedRouteLatLngs = [];
    const myToken = ++this.routeDrawToken;

    const url = `${this.OSRM_URL}${startCoords[1]},${startCoords[0]};${endCoords[1]},${endCoords[0]}?overview=full&geometries=geojson`;

    fetch(url)
      .then(res => res.json())
      .then(data => {
        if (myToken !== this.routeDrawToken) return; // user switched/closed
        if (!data.routes?.[0]) return;

        // Cache the geometry
        this.cachedRouteLatLngs = data.routes[0].geometry.coordinates.map(
          (c: number[]) => [c[1], c[0]] as [number, number]
        );
        this.cachedRoute = { startCity, endCity };
        this.activeRouteTruckId = truck.truck_id;

        // Create the two polylines (they'll live until route changes or panel closes)
        this.completedPolyline = L.polyline([], {
          color: '#00e676', weight: 5, opacity: 0.9, lineCap: 'round', lineJoin: 'round'
        }).addTo(this.map);

        this.remainingPolyline = L.polyline([], {
          color: '#00b4ff', weight: 5, opacity: 0.9,
          dashArray: '10, 10', lineCap: 'round', lineJoin: 'round'
        }).addTo(this.map);

        // Set initial split
        this.updatePolylineSplit(truck);

        // Fit bounds once on first load
        const bounds = L.latLngBounds(this.cachedRouteLatLngs);
        this.map.fitBounds(bounds, { padding: [100, 100], maxZoom: 13 });
      })
      .catch(err => console.error('Route fetch error:', err));
  }

  /**
   * Moves the completed/remaining split point to the truck's current animated position.
   * Zero fetches, zero flicker — just updates the existing polyline coordinates.
   */
  private updatePolylineSplit(truck: Truck): void {
    if (!this.completedPolyline || !this.remainingPolyline) return;
    if (this.cachedRouteLatLngs.length === 0) return;

    const state = this.truckStates.get(truck.truck_id);
    const now   = performance.now();
    let truckPos: [number, number];

    if (state) {
      const t = Math.min((now - state.lastUpdateTime) / this.ANIMATION_DURATION, 1);
      const e = this.EASING(t);
      truckPos = [
        state.currentLat + (state.targetLat - state.currentLat) * e,
        state.currentLng + (state.targetLng - state.currentLng) * e
      ];
    } else {
      truckPos = [truck.latitude, truck.longitude];
    }

    const splitIndex    = this.findClosestPointIndex(truckPos, this.cachedRouteLatLngs);
    const completedPath = [...this.cachedRouteLatLngs.slice(0, splitIndex + 1), truckPos];
    const remainingPath = [truckPos, ...this.cachedRouteLatLngs.slice(splitIndex + 1)];

    // setLatLngs updates the existing polyline in-place — no DOM removal/re-add
    this.completedPolyline.setLatLngs(completedPath);
    this.remainingPolyline.setLatLngs(remainingPath);
  }

  private destroyPolylines(): void {
    if (this.completedPolyline) { this.map.removeLayer(this.completedPolyline); this.completedPolyline = null; }
    if (this.remainingPolyline) { this.map.removeLayer(this.remainingPolyline); this.remainingPolyline = null; }
  }

  // ─────────────────────────────────────────────
  // Data loading
  // ─────────────────────────────────────────────

  loadTrucks(): void {
    this.truckService.getTrucks().subscribe({
      next: (data) => {
        this.trucks = [...data];
        this.isLoading = false;
        this.lastUpdated = new Date();
        this.updateMarkers(data);

        if (this.selectedTruck) {
          const updated = data.find(t => t.truck_id === this.selectedTruck!.truck_id);
          if (updated) {
            const posChanged =
              updated.latitude  !== this.selectedTruck.latitude ||
              updated.longitude !== this.selectedTruck.longitude;
            this.selectedTruck = updated;

            // Position changed: update the split point on the CACHED geometry
            // No fetch, no flicker — just move the dividing point along the line
            if (posChanged) this.updatePolylineSplit(updated);
          } else {
            this.selectedTruck = null;
            this.activeRouteTruckId = null;
            this.routeDrawToken++;
            this.destroyPolylines();
            this.cachedRouteLatLngs = [];
            this.cachedRoute = null;
          }
        }

        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('API ERROR:', err);
        this.isLoading = false;
        this.cdr.detectChanges();
      }
    });
  }

  private updateMarkers(trucks: Truck[]): void {
    const L = (window as any).L;
    if (!this.map || !L) return;
    const now = performance.now();

    trucks.forEach(truck => {
      const color = this.getAnomalyColor(truck.anomaly);
      const icon  = L.divIcon({
        className: '',
        html: `<div class="truck-marker ${truck.anomaly !== 'none' ? 'pulse' : ''}" style="background:${color}">
                 <span>🚛</span>
               </div>`,
        iconSize: [40, 40],
        iconAnchor: [20, 20]
      });

      if (this.truckStates.has(truck.truck_id)) {
        const state = this.truckStates.get(truck.truck_id)!;

        // Snapshot current interpolated position before shifting target
        const elapsed = now - state.lastUpdateTime;
        const t = Math.min(elapsed / this.ANIMATION_DURATION, 1);
        const e = this.EASING(t);
        state.currentLat = state.currentLat + (state.targetLat - state.currentLat) * e;
        state.currentLng = state.currentLng + (state.targetLng - state.currentLng) * e;

        state.targetLat = truck.latitude;
        state.targetLng = truck.longitude;
        state.lastUpdateTime = now;

        state.marker.setIcon(icon);
      } else {
        const marker = L.marker([truck.latitude, truck.longitude], { icon })
          .addTo(this.map)
          .on('click', () => this.selectTruck(truck));

        this.truckStates.set(truck.truck_id, {
          marker,
          currentLat: truck.latitude,
          currentLng: truck.longitude,
          targetLat:  truck.latitude,
          targetLng:  truck.longitude,
          lastUpdateTime: now
        });
      }
    });

    const liveIds = new Set(trucks.map(t => t.truck_id));
    this.truckStates.forEach((state, id) => {
      if (!liveIds.has(id)) {
        this.map.removeLayer(state.marker);
        this.truckStates.delete(id);
      }
    });
  }

  // ─────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────

  private findClosestPointIndex(target: [number, number], path: [number, number][]): number {
    let minDist = Infinity, minIndex = 0;
    for (let i = 0; i < path.length; i++) {
      const d = this.haversine(target[0], target[1], path[i][0], path[i][1]);
      if (d < minDist) { minDist = d; minIndex = i; }
    }
    return minIndex;
  }

  private haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371, dLat = (lat2 - lat1) * Math.PI / 180, dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  private getCityCoords(cityName: string): [number, number] | null {
    const cities: Record<string, [number, number]> = {
      'Casablanca': [33.5731, -7.5898], 'Rabat': [34.0209, -6.8416],
      'Marrakech': [31.6295, -8.0089],  'Tanger': [35.7595, -5.8126],
      'Agadir': [30.4278, -9.5981],     'Fes': [34.0346, -4.9806],
      'Meknes': [33.8933, -5.5551],     'Oujda': [34.6818, -1.9116],
      'Nador': [35.1686, -2.9331],      'Kenitra': [34.2610, -6.5897],
      'El Jadida': [33.2550, -8.5070],  'Safi': [32.2990, -9.2338],
      'Tetouan': [35.5713, -5.3689],    'Beni Mellal': [32.3378, -6.3700],
      'Khouribga': [33.6111, -6.9058],  'Settat': [33.0113, -7.6111],
      'Ifrane': [33.5265, -5.1169],     'Essaouira': [31.5085, -9.7594],
      'Ouarzazate': [30.9333, -6.9094], 'Al Hoceima': [35.2513, -3.9343]
    };
    return cities[cityName] || null;
  }

  getAnomalyColor(anomaly: string): string {
    switch (anomaly) {
      case 'overheat':  return '#ff4d4d';
      case 'overspeed': return '#ff9500';
      case 'fuel_leak': return '#ffdd00';
      default:          return '#00e676';
    }
  }

  getAnomalyIcon(anomaly: string): string {
    switch (anomaly) {
      case 'overheat':  return '🔥';
      case 'overspeed': return '⚡';
      case 'fuel_leak': return '💧';
      default:          return '✅';
    }
  }

  getStatusClass(anomaly: string): string {
    return anomaly === 'none' ? 'status-ok' : 'status-alert';
  }

  get normalCount(): number { return this.trucks.filter(t => t.anomaly === 'none').length; }
  get alertCount():  number { return this.trucks.filter(t => t.anomaly !== 'none').length; }
  get avgSpeed():    number {
    if (!this.trucks.length) return 0;
    return Math.round(this.trucks.reduce((s, t) => s + t.speed, 0) / this.trucks.length);
  }
}