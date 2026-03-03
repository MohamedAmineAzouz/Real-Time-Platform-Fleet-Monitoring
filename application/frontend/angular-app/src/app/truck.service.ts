import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Truck {
  truck_id: number;
  latitude: number;
  longitude: number;
  speed: number;
  fuel_level: number;
  engine_temp: number;
  driver_id: string;
  start_city: string;
  end_city: string;
  odometer_km: number;
  refueling: boolean;
  refuel_city: string | null;
  anomaly: string;
  theft: boolean;
  timestamp: string; 
}
@Injectable({
  providedIn: 'root'
})
export class TruckService {

  private apiUrl = '/trucks';

  constructor(private http: HttpClient) {}

  getTrucks(): Observable<Truck[]> {
    return this.http.get<Truck[]>(this.apiUrl);
  }
}