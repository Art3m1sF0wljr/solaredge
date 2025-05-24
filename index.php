<?php
// Configuration
$LOG_FILE = __DIR__ . '/solar_edge_data.log';
$PLOT_DAYS = 3;
$SMOOTHING_WINDOW = 5;

// Function to parse the log file
function parse_log_file($filename) {
    $data = array();
    if (!file_exists($filename)) {
        return $data;
    }
    
    $lines = file($filename, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        $parts = explode(', ', $line);
        if (count($parts) < 5) continue;
        
        try {
            $timestamp = DateTime::createFromFormat('Y-m-d\TH:i:s.u', $parts[0]);
            if (!$timestamp) continue;
            
            $ac_power = (float)explode(' ', explode(': ', $parts[1])[1])[0];
            $dc_power = (float)explode(' ', explode(': ', $parts[2])[1])[0];
            $state = explode(': ', $parts[3])[1];
            $energy = (float)explode(' ', explode(': ', $parts[4])[1])[0] * 1000; // MWh to kWh
            
            $data[] = array(
                'timestamp' => $timestamp,
                'ac_power' => $ac_power,
                'dc_power' => $dc_power,
                'state' => $state,
                'energy' => $energy
            );
        } catch (Exception $e) {
            continue;
        }
    }
    
    return $data;
}

// Function to filter last N days
function filter_last_days($data, $days) {
    $cutoff = new DateTime();
    $cutoff->sub(new DateInterval('P'.$days.'D'));
    
    return array_filter($data, function($item) use ($cutoff) {
        return $item['timestamp'] >= $cutoff;
    });
}

// Function to calculate power from energy differences
function calculate_energy_derivative($data) {
    global $SMOOTHING_WINDOW;
    if (empty($data)) return $data;
    
    // Sort by timestamp
    usort($data, function($a, $b) {
        if ($a['timestamp'] == $b['timestamp']) {
            return 0;
        }
        return ($a['timestamp'] < $b['timestamp']) ? -1 : 1;
    });
    
    $prev = null;
    foreach ($data as &$item) {
        if ($prev === null) {
            $item['power_from_energy'] = 0;
            $prev = $item;
            continue;
        }
        
        $time_diff = $item['timestamp']->getTimestamp() - $prev['timestamp']->getTimestamp();
        $energy_diff = ($item['energy'] - $prev['energy']) * 1000; // kWh to Wh
        
        if ($time_diff > 0) {
            $item['power_from_energy'] = $energy_diff / ($time_diff / 3600); // Wh to W
        } else {
            $item['power_from_energy'] = 0;
        }
        
        $prev = $item;
    }
    unset($item); // Break the reference
    
    // Apply smoothing
    $count = count($data);
    for ($i = 0; $i < $count; $i++) {
        $window = array();
        $start = max(0, $i - floor($SMOOTHING_WINDOW/2));
        $end = min($count-1, $i + floor($SMOOTHING_WINDOW/2));
        for ($j = $start; $j <= $end; $j++) {
            $window[] = $data[$j]['power_from_energy'];
        }
        $data[$i]['power_from_energy_smoothed'] = array_sum($window) / count($window);
    }
    
    return $data;
}

// Process the data
$data = parse_log_file($LOG_FILE);
$filtered_data = filter_last_days($data, $PLOT_DAYS);
$processed_data = calculate_energy_derivative($filtered_data);

// Prepare data for JavaScript (with 5kW clipping)
$timestamps = array();
$ac_power = array();
$dc_power = array();
$power_from_energy = array();
$power_from_energy_smoothed = array();

foreach ($processed_data as $item) {
    $timestamps[] = $item['timestamp']->format('Y-m-d H:i:s');
    $ac_power[] = min($item['ac_power'] / 1000, 5); // Clip to 5kW max
    $dc_power[] = min($item['dc_power'] / 1000, 5); // Clip to 5kW max
    $power_from_energy[] = min(isset($item['power_from_energy']) ? $item['power_from_energy'] / 1000 : 0, 5);
    $power_from_energy_smoothed[] = min(isset($item['power_from_energy_smoothed']) ? $item['power_from_energy_smoothed'] / 1000 : 0, 5);
}
?>
<!DOCTYPE html>
<html>
<head>
    <title>SolarEdge Power Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@2.9.4"></script>
    <script src="https://cdn.jsdelivr.net/npm/moment@2.29.1"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-moment@1.0.0"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
        }
        .chart-container {
            width: 100%;
            max-width: 1200px;
            margin: 0 auto 30px auto;
            overflow: hidden;
        }
        canvas {
            display: block;
        }
        .refresh-btn {
            background-color: #4CAF50;
            border: none;
            color: white;
            padding: 10px 20px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 16px;
            margin: 10px 2px;
            cursor: pointer;
            border-radius: 5px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>SolarEdge Power Monitor</h1>
        <button class="refresh-btn" onclick="window.location.reload()">Refresh Data</button>
    </div>
    
    <div class="chart-container">
        <canvas id="powerChart"></canvas>
    </div>
    
    <div class="chart-container">
        <canvas id="energyDerivativeChart"></canvas>
    </div>
    
    <script>
        // Prepare data
        var timestamps = <?php echo json_encode($timestamps); ?>;
        var acPower = <?php echo json_encode($ac_power); ?>;
        var dcPower = <?php echo json_encode($dc_power); ?>;
        var powerFromEnergy = <?php echo json_encode($power_from_energy); ?>;
        var powerFromEnergySmoothed = <?php echo json_encode($power_from_energy_smoothed); ?>;
        
        // Power Chart (AC and DC)
        var powerCtx = document.getElementById('powerChart').getContext('2d');
        var powerChart = new Chart(powerCtx, {
            type: 'line',
            data: {
                labels: timestamps,
                datasets: [
                    {
                        label: 'AC Power (kW)',
                        data: acPower,
                        borderColor: 'blue',
                        backgroundColor: 'rgba(0, 0, 255, 0.1)',
                        borderWidth: 1.5,
                        pointRadius: 0
                    },
                    {
                        label: 'DC Power (kW)',
                        data: dcPower,
                        borderColor: 'green',
                        backgroundColor: 'rgba(0, 255, 0, 0.1)',
                        borderWidth: 1.5,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    xAxes: [{
                        type: 'time',
                        time: {
                            unit: 'hour',
                            displayFormats: {
                                hour: 'MMM D HH:mm'
                            }
                        },
                        scaleLabel: {
                            display: true,
                            labelString: 'Time'
                        }
                    }],
                    yAxes: [{
                        scaleLabel: {
                            display: true,
                            labelString: 'Power (kW)'
                        },
                        ticks: {
                            min: 0,
                            max: 5,
                            stepSize: 1,
                            callback: function(value) {
                                return value + ' kW';
                            }
                        },
                        afterBuildTicks: function(scale) {
                            scale.max = 5;
                            scale.min = 0;
                        }
                    }]
                },
                title: {
                    display: true,
                    text: 'Direct Power Measurements (Last <?php echo $PLOT_DAYS; ?> Days)'
                }
            }
        });
        
        // Energy Derivative Chart
        var energyCtx = document.getElementById('energyDerivativeChart').getContext('2d');
        var energyChart = new Chart(energyCtx, {
            type: 'line',
            data: {
                labels: timestamps,
                datasets: [
                    {
                        label: 'Instantaneous Power',
                        data: powerFromEnergy,
                        borderColor: 'red',
                        backgroundColor: 'rgba(255, 0, 0, 0.1)',
                        borderWidth: 1,
                        pointRadius: 0
                    },
                    {
                        label: 'Smoothed Power',
                        data: powerFromEnergySmoothed,
                        borderColor: 'red',
                        backgroundColor: 'rgba(255, 0, 0, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                scales: {
                    xAxes: [{
                        type: 'time',
                        time: {
                            unit: 'hour',
                            displayFormats: {
                                hour: 'MMM D HH:mm'
                            }
                        },
                        scaleLabel: {
                            display: true,
                            labelString: 'Time'
                        }
                    }],
                    yAxes: [{
                        scaleLabel: {
                            display: true,
                            labelString: 'Power (kW)'
                        },
                        ticks: {
                            min: 0,
                            max: 5,
                            stepSize: 1,
                            callback: function(value) {
                                return value + ' kW';
                            }
                        },
                        afterBuildTicks: function(scale) {
                            scale.max = 5;
                            scale.min = 0;
                        }
                    }]
                },
                title: {
                    display: true,
                    text: 'Power Calculated from Energy Differences (ΔE/Δt)'
                }
            }
        });
    </script>
</body>
</html>
