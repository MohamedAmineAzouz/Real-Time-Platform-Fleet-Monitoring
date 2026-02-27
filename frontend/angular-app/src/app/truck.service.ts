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
  anomaly: string;
  start_city_lat: number;
  start_city_lon: number;
  end_city_lat: number;  
  end_city_lon: number;  
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