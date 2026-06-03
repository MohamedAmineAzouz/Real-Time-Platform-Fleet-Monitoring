import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Truck {
  truck_id:               number;
  processed_at:           string;
  event_time:             string;
  latitude:               number;
  longitude:              number;
  speed:                  number;
  fuel_level:             number;
  engine_temp:            number;
  driver_id:              string;
  start_city:             string;
  end_city:               string;
  odometer_km:            number;
  refueling:              boolean;
  refuel_city:            string | null;
  anomaly:                string;
  theft:                  boolean;
  theft_amount:           number | null;
  alert_type:             string;
  is_alert:               boolean;
  distance_km:            number;
  fuel_used:              number;
  fuel_consumption_rate:  number;
  high_consumption:       boolean;
  fuel_consumed_trip:     number;
  fuel_refueled:          number;
  driver_name:            string | null;
  truck_model:            string | null;
  in_maintenance:         boolean;
  maintenance_type:       string | null;
  maintenance_desc:       string | null;
}

@Injectable({ providedIn: 'root' })
export class TruckService {
  private apiUrl = '/api';

  constructor(private http: HttpClient) {}

  getTrucks(): Observable<Truck[]> {
    return this.http.get<Truck[]>(`${this.apiUrl}/trucks`);
  }

  getTruckHistory(truckId: number, limit = 100): Observable<Truck[]> {
    return this.http.get<Truck[]>(`${this.apiUrl}/trucks/${truckId}/history?limit=${limit}`);
  }
}