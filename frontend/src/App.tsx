
import { useState } from 'react'

const API_URL = 'http://127.0.0.1:8000'

interface AirQualityResponse {
  location: {
    name: string
    latitude: number
    longitude: number
    country?: string | null
    timezone?: string | null
  }
  current: {
    timestamp: string
    us_aqi: {
      value: number | null
      category: string
      description: string
      color: string
    }
    european_aqi: number | null
    pollutants: {
      pm2_5: number | null
      pm10: number | null
      nitrogen_dioxide: number | null
      ozone: number | null
      sulphur_dioxide: number | null
      carbon_monoxide: number | null
    }
    units: Record<string, string>
  }
  summary: string
}

function App() {
  const [location, setLocation] = useState('Bengaluru')
  const [data, setData] = useState<AirQualityResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const searchCity = async () => {
    const city = location.trim()

    if (!city) {
      setError('Please enter a city name.')
      return
    }

    setLoading(true)
    setError('')
    setData(null)

    try {
      const response = await fetch(
        `${API_URL}/api/air-quality?city=${encodeURIComponent(city)}`
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(
          errorData.detail || 'Unable to retrieve air quality data.'
        )
      }

      const result: AirQualityResponse = await response.json()
      setData(result)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Something went wrong. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  const pollutants = [
    {
      name: 'PM2.5',
      description: 'Fine particles',
      value: data?.current.pollutants.pm2_5,
      unit: 'pm2_5',
    },
    {
      name: 'PM10',
      description: 'Coarse particles',
      value: data?.current.pollutants.pm10,
      unit: 'pm10',
    },
    {
      name: 'NO₂',
      description: 'Nitrogen dioxide',
      value: data?.current.pollutants.nitrogen_dioxide,
      unit: 'nitrogen_dioxide',
    },
    {
      name: 'O₃',
      description: 'Ozone',
      value: data?.current.pollutants.ozone,
      unit: 'ozone',
    },
    {
      name: 'SO₂',
      description: 'Sulphur dioxide',
      value: data?.current.pollutants.sulphur_dioxide,
      unit: 'sulphur_dioxide',
    },
    {
      name: 'CO',
      description: 'Carbon monoxide',
      value: data?.current.pollutants.carbon_monoxide,
      unit: 'carbon_monoxide',
    },
  ]

  const formatValue = (value: number | null | undefined) => {
    return value == null ? '--' : Number(value.toFixed(2)).toString()
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <nav className="flex items-center justify-between border-b border-slate-800 px-8 py-5">
        <h1 className="text-2xl font-bold tracking-tight">
          <span className="text-emerald-400">Air</span>Aware
        </h1>
        <span className="text-sm text-slate-400">
          Your personal air quality assistant
        </span>
      </nav>

      <main className="mx-auto max-w-7xl px-6 py-10">
        <section className="mb-10">
          <p className="mb-3 text-sm font-medium uppercase tracking-widest text-emerald-400">
            Breathe smarter. Live healthier.
          </p>

          <h2 className="text-4xl font-bold md:text-5xl">
            Understand the air <br /> around you.
          </h2>

          <p className="mt-4 max-w-xl text-slate-400">
            Get air quality insights and personalised recommendations
            to protect your everyday health.
          </p>
        </section>

        {/* City search */}
        <section className="mb-8 flex max-w-xl gap-3">
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') searchCity()
            }}
            placeholder="Enter your city..."
            className="w-full rounded-xl border border-slate-700 bg-slate-900 px-5 py-3 outline-none focus:border-emerald-400"
          />

          <button
            onClick={searchCity}
            disabled={loading}
            className="rounded-xl bg-emerald-400 px-6 py-3 font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Search'}
          </button>
        </section>

        {/* Error message */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Air quality overview */}
        <section className="grid gap-6 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 md:col-span-2">
            <p className="text-sm text-slate-400">
              Air quality overview
            </p>

            <h3 className="mt-2 text-2xl font-semibold">
              {data
                ? `${data.location.name}${data.location.country ? `, ${data.location.country}` : ''}`
                : location}
            </h3>

            <p className="mt-1 text-xs text-slate-500">
              {data
                ? 'Source: Open-Meteo · Model-based air quality estimate · US AQI'
                : 'Search a city to retrieve air quality data.'}
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-8">
              <div>
                <p
                  className="text-7xl font-bold"
                  style={{
                    color: data?.current.us_aqi.color || '#10b981',
                  }}
                >
                  {data?.current.us_aqi.value ?? '--'}
                </p>

                <p className="mt-2 text-sm text-slate-400">
                  US AQI
                </p>
              </div>

              <div className="max-w-md">
                <p className="text-xl font-semibold">
                  {loading
                    ? 'Fetching air quality...'
                    : data?.current.us_aqi.category || 'Awaiting data'}
                </p>

                <p className="mt-2 text-sm leading-6 text-slate-400">
                  {data
                    ? data.current.us_aqi.description
                    : 'Search for a city to see its current air quality information.'}
                </p>
              </div>
            </div>

            {data && (
              <div className="mt-8 border-t border-slate-800 pt-4 text-xs text-slate-500">
                European AQI: {data.current.european_aqi ?? '--'}
                <br />
                Updated: {data.current.timestamp}
              </div>
            )}
          </div>

          {/* Daily insight */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">
              Your daily insight
            </p>

            <div className="mt-6 text-4xl">🌿</div>

            <h3 className="mt-4 text-xl font-semibold">
              {data?.current.us_aqi.category || 'Breathe better'}
            </h3>

            <p className="mt-2 text-sm leading-6 text-slate-400">
              {data
                ? data.summary
                : 'Air quality information and personalised guidance will appear here after your city search.'}
            </p>
          </div>
        </section>

        {/* Pollutant monitoring */}
        <section className="mt-8">
          <h3 className="mb-4 text-xl font-semibold">
            Pollutant monitoring
          </h3>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {pollutants.map((pollutant) => (
              <div
                key={pollutant.name}
                className="rounded-2xl border border-slate-800 bg-slate-900 p-5"
              >
                <p className="text-lg font-semibold">
                  {pollutant.name}
                </p>

                <p className="mt-2 text-sm text-slate-400">
                  {pollutant.description}
                </p>

                <p className="mt-5 text-2xl font-bold text-emerald-400">
                  {formatValue(pollutant.value)}
                </p>

                <p className="text-xs text-slate-500">
                  {pollutant.value == null
                    ? 'No reading available'
                    : data?.current.units[pollutant.unit] || 'Unit unavailable'}
                </p>
              </div>
            ))}
          </div>
        </section>

        <footer className="mt-16 border-t border-slate-800 py-6 text-center text-sm text-slate-500">
          AirAware · Making every breath count.
        </footer>
      </main>
    </div>
  )
}

export default App
