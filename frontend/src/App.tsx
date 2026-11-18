
import { useState } from 'react'

function App() {
  const [location, setLocation] = useState('Bengaluru')
  const [searchedLocation, setSearchedLocation] = useState('Bengaluru')

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <nav className="flex items-center justify-between border-b border-slate-800 px-8 py-5">
        <h1 className="text-2xl font-bold tracking-tight">
          <span className="text-emerald-400">Air</span>Aware
        </h1>
        <span className="text-sm text-slate-400">Your personal air quality assistant</span>
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

        <section className="mb-8 flex max-w-xl gap-3">
          <input
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setSearchedLocation(location)
            }}
            placeholder="Enter your city..."
            className="w-full rounded-xl border border-slate-700 bg-slate-900 px-5 py-3 outline-none focus:border-emerald-400"
          />
          <button
            onClick={() => setSearchedLocation(location)}
            className="rounded-xl bg-emerald-400 px-6 py-3 font-semibold text-slate-950 hover:bg-emerald-300"
          >
            Search
          </button>
        </section>

        <section className="grid gap-6 md:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 md:col-span-2">
            <p className="text-sm text-slate-400">Air quality overview</p>
            <h3 className="mt-2 text-2xl font-semibold">{searchedLocation}</h3>
            <p className="mt-1 text-xs text-amber-300">
              Preview dashboard · Sample values, not live readings
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-8">
              <div>
                <p className="text-7xl font-bold text-emerald-400">--</p>
                <p className="mt-2 text-sm text-slate-400">AQI</p>
              </div>
              <div>
                <p className="text-xl font-semibold">Awaiting data</p>
                <p className="mt-2 text-sm text-slate-400">
                  Connect an air quality data source to see current conditions.
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
            <p className="text-sm text-slate-400">Your daily insight</p>
            <div className="mt-6 text-4xl">🌿</div>
            <h3 className="mt-4 text-xl font-semibold">Breathe better</h3>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Your personalised health and outdoor activity guidance will
              appear here once live air quality data is connected.
            </p>
          </div>
        </section>

        <section className="mt-8">
          <h3 className="mb-4 text-xl font-semibold">Pollutant monitoring</h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ['PM2.5', 'Fine particles'],
              ['PM10', 'Coarse particles'],
              ['NO₂', 'Nitrogen dioxide'],
              ['O₃', 'Ozone'],
            ].map(([name, description]) => (
              <div key={name} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <p className="text-lg font-semibold">{name}</p>
                <p className="mt-2 text-sm text-slate-400">{description}</p>
                <p className="mt-5 text-2xl font-bold text-slate-500">--</p>
                <p className="text-xs text-slate-500">Waiting for readings</p>
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
