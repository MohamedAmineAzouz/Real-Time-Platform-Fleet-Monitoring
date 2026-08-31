import pandas as pd
from utils.cassandra_client import query_df

def _format_df_markdown(df: pd.DataFrame) -> str:
    """Format DataFrame as markdown table, falling back to to_string if tabulate is absent."""
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.to_string(index=False)

def get_weekly_summary_context() -> str:
    """Fetch and format weekly summaries as markdown."""
    try:
        df = query_df("SELECT * FROM batch_weekly_summary")
        if df.empty:
            return "No weekly summary data available."
        
        # Select key columns for context
        cols = [
            'week_id', 'total_distance_km', 'total_fuel_consumed_l',
            'avg_fuel_per_100km', 'total_alerts', 'fleet_utilization_avg'
        ]
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy()
        
        # Sort by week_id descending
        if 'week_id' in df_subset.columns:
            df_subset = df_subset.sort_values('week_id', ascending=False).head(4)
            
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving weekly summary: {e}"

def get_route_efficiency_context() -> str:
    """Fetch and format route efficiencies as markdown."""
    try:
        df = query_df("SELECT * FROM batch_route_efficiency")
        if df.empty:
            return "No route efficiency data available."
        
        cols = [
            'stat_date', 'start_city', 'end_city', 'total_trips',
            'avg_distance_km', 'avg_fuel_l', 'avg_fuel_per_100km',
            'avg_speed_kmh', 'avg_alerts_per_trip'
        ]
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy()
        
        # Sort by stat_date descending
        if 'stat_date' in df_subset.columns:
            df_subset = df_subset.sort_values('stat_date', ascending=False).head(15)
            
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving route efficiency: {e}"

def get_maintenance_flags_context() -> str:
    """Fetch and format maintenance flags as markdown."""
    try:
        df = query_df("SELECT * FROM batch_maintenance_flags")
        if df.empty:
            return "No maintenance flag data available."
        
        cols = [
            'stat_date', 'truck_id', 'avg_engine_temp', 'max_engine_temp',
            'overheat_count', 'flag_high_temp', 'flag_overheat_alerts',
            'flag_fuel_inconsistency', 'maintenance_needed', 'priority'
        ]
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy()
        
        # Filter for trucks needing maintenance or having high priorities
        if 'maintenance_needed' in df_subset.columns:
            df_subset = df_subset[df_subset['maintenance_needed'] == True].head(10)
            
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving maintenance flags: {e}"

def get_fuel_waste_anomalies_context() -> str:
    """Fetch and format fuel waste anomalies as markdown."""
    try:
        df = query_df("SELECT * FROM batch_fuel_waste_anomalies")
        if df.empty:
            return "No fuel waste anomaly data available."
        
        cols = [
            'stat_date', 'truck_id', 'total_distance_km', 'total_fuel_l',
            'fuel_per_100km', 'fleet_median_fuel_per_100km', 'waste_vs_median_pct', 'is_anomaly'
        ]
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy()
        
        # Filter for anomalies
        if 'is_anomaly' in df_subset.columns:
            df_subset = df_subset[df_subset['is_anomaly'] == True].head(10)
            
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving fuel waste anomalies: {e}"

def get_daily_truck_stats_context() -> str:
    """Fetch and format daily truck stats as markdown."""
    try:
        df = query_df("SELECT * FROM batch_daily_truck_stats")
        if df.empty:
            return "No daily truck statistics available."
        
        cols = [
            'stat_date', 'truck_id', 'total_distance_km', 'total_fuel_consumed_l',
            'fuel_per_100km', 'avg_speed_kmh', 'max_speed_kmh', 'total_alerts',
            'overspeed_count', 'overheat_count', 'fuel_theft_count', 'low_fuel_count'
        ]
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy()
        
        # Sort by date / stats descending
        if 'stat_date' in df_subset.columns:
            df_subset = df_subset.sort_values(['stat_date', 'total_alerts'], ascending=[False, False]).head(20)
            
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving daily truck stats: {e}"

def get_drivers_context() -> str:
    """Fetch and format drivers registry as markdown."""
    try:
        df = query_df("SELECT * FROM drivers")
        if df.empty:
            return "No driver registry data available."
        cols = ['driver_id', 'name', 'license_number', 'phone', 'status', 'current_truck_id']
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy().head(20)
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving drivers: {e}"

def get_trucks_context() -> str:
    """Fetch and format trucks registry as markdown."""
    try:
        df = query_df("SELECT * FROM trucks")
        if df.empty:
            return "No truck registry data available."
        cols = ['truck_id', 'license_plate', 'model', 'year', 'status', 'fuel_capacity', 'max_load_kg']
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy().head(20)
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving trucks: {e}"

def get_trajets_context() -> str:
    """Fetch and format standard trajets (routes) as markdown."""
    try:
        df = query_df("SELECT * FROM trajets")
        if df.empty:
            return "No trajets route data available."
        cols = ['start_city', 'end_city', 'distance_km']
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy().head(20)
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving trajets: {e}"

def get_driver_performance_context() -> str:
    """Fetch and format batch driver performance rankings as markdown."""
    try:
        df = query_df("SELECT * FROM batch_driver_performance")
        if df.empty:
            return "No driver performance rankings available."
        cols = [
            'stat_date', 'driver_id', 'fleet_rank', 'performance_score',
            'speed_compliance_rate', 'fuel_per_100km', 'alert_rate_per_100',
            'theft_events', 'total_distance_km'
        ]
        available_cols = [c for c in cols if c in df.columns]
        df_subset = df[available_cols].copy()
        if 'stat_date' in df_subset.columns:
            df_subset = df_subset.sort_values(['stat_date', 'fleet_rank'], ascending=[False, True]).head(15)
        return _format_df_markdown(df_subset)
    except Exception as e:
        return f"Error retrieving driver performance: {e}"

def retrieve_all_context() -> str:
    """Retrieve and combine all contexts into one comprehensive prompt context string."""
    context_blocks = []
    
    context_blocks.append("### DRIVER REGISTRY (ID, NAME, CURRENT TRUCK)\n" + get_drivers_context())
    context_blocks.append("### FLEET VEHICLES REGISTRY (TRUCKS, MODELS, SPECS)\n" + get_trucks_context())
    context_blocks.append("### STANDARD CORRIDORS & TRAJETS\n" + get_trajets_context())
    context_blocks.append("### BATCH DRIVER PERFORMANCE & RANKINGS\n" + get_driver_performance_context())
    context_blocks.append("### WEEKLY SUMMARY PERFORMANCE METRICS\n" + get_weekly_summary_context())
    context_blocks.append("### ROUTE/CORRIDOR OPERATIONAL EFFICIENCY\n" + get_route_efficiency_context())
    context_blocks.append("### DAILY TRUCK STATISTICS (TOP ALERT/VOLUME VEHICLES)\n" + get_daily_truck_stats_context())
    context_blocks.append("### MAINTENANCE FLAGS & OVERHEAT ALERTS\n" + get_maintenance_flags_context())
    context_blocks.append("### FUEL WASTE AND ANOMALOUS CONSUMPTION\n" + get_fuel_waste_anomalies_context())
    
    return "\n\n".join(context_blocks)
